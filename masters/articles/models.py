from django.db import transaction
from django.contrib.gis.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver
from django_socketio import broadcast, broadcast_channel, NoSocket
from pattern.web import Spider, BREADTH, DEPTH, plaintext, Element, Link, URL
from django.contrib.gis.utils import LayerMapping
from django.contrib.gis.gdal import DataSource		
from django.contrib.gis.geos import GEOSGeometry
from django.conf import settings
from django.core.cache import cache
from nltk.tokenize import sent_tokenize
import datetime
import re
import os
import nltk
import numpy
import operator

# Initial Weightings
PARISH_WEIGHTING = 20
COMMUNITY_WEIGHTING = 10
# Scoring
PARISH_PRESENT_WEIGHTING = 15
COMMON_WEIGHTING = -10
NOT_LOWER_CASED_WEIGHTING = 5
NO_NEAR_PRONOUN_WEIGHTING = 20
WITHIN_ONE_STDEV_WEIGHTING = 10
NLTK_NE_TAG_WEIGHTING = 10
PASS_MARK = 35
# Tests
PARISH_PRESENT = "PP"
COMMON = "COM"
NOT_LOWER_CASED = "NLC"
NO_NEAR_PRONOUN = "NNP"
WITHIN_ONE_STDEV = "WOS"
NLTK_NE = "NE"
HAS_COMMON_PREFIX = "HCF"

TESTS = [PARISH_PRESENT, COMMON, NOT_LOWER_CASED, NO_NEAR_PRONOUN, WITHIN_ONE_STDEV, NLTK_NE, HAS_COMMON_PREFIX]

class References(models.Model):

	class Meta:
		abstract = True

	references = []
	occurrences = {} # occurrences of a particular gazetteer
	centroid = None

	def __init__(self, article_references=None):
		self.references = []
		self.occurrences = {}
		self.centroid = None
		self.std = 0

		if article_references:
			for article_reference in article_references:
				self.add_reference(article_reference, False)
			self.update_distances()

	def __getitem__(self, key):
		return self.references[key]

	def len(self):
		return len(self.references)

	@staticmethod
	def from_article(article):
		return References(article.article_references.all())

	@staticmethod
	def from_article_id(article_id):
		article = Article.objects.get(pk=article_id)
		return References.from_article(article)

	@staticmethod
	def from_article_reference(article_reference):
		return References(article_reference.article.article_references.all())

	@staticmethod
	def from_article_reference_id(article_reference_id):
		article_reference = ArticleReference.objects.get(pk=article_reference_id)
		return References.from_article_reference(article_reference)
	
	def remove_failed_references(self):
		final_references = []
		for reference in self.references:
			if reference.weighting >= PASS_MARK:
				final_references.append(reference)
			else:
				print "[WW] - Removing failed reference: %s - %s\n\t: %s" % (reference, reference.weighting, reference.sentence)
		self.references = final_references

	def get_references_by_level(self, level):
		""" Returns the references for a level
		"""
		return [ reference for reference in self.references if reference.gazetteer.level == level ]

	def get_occurrences(self, reference):
		""" Returns the number of occurrences of a particular gazetteer
		"""
		if type(reference) == Gazetteer:
			pk = reference.pk
		else:
			pk = reference.gazetteer.pk
		return self.occurrences.get(pk, 0)

	def add_reference(self, reference, update_distance=True):
		""" Adds a reference
		"""
		#print "[II]   Adding reference %s" % reference.reference
		reference.references = self
		self.references.append(reference)
		reference.weighting = PARISH_WEIGHTING if reference.gazetteer.level == 1 else COMMUNITY_WEIGHTING
		# Increase the occurrences
		occurrences = self.occurrences.get(reference.gazetteer.pk, 0)
		self.occurrences[reference.gazetteer.pk] = occurrences + 1
		if update_distance:
			self.update_distances()
	
	def get_references_for_gazetteer(self, gazetteer):
		""" Returns all references to the given gazetteer
		"""
		return [ reference for reference in self.references if reference.gazetteer == gazetteer ]

	def update_distances(self):
		""" Updates the centroid and recalculates the distances to the centroid 
			for each reference
		"""
		#print "[II]   Updating centroid...."
		ids = [ reference.gazetteer.pk for reference in self.references ]

		self.centroid = Gazetteer.objects.filter(pk__in=ids).collect().centroid
		#print "[II]   Centroid updated to: %s" % self.centroid
		# Update the distances on the reference objects
		gazetteers = Gazetteer.objects.filter(pk__in=ids).distance(self.centroid)
		distances = [ g.distance.km for g in gazetteers ]
		# calculate the std and mean
		array = numpy.array(distances)
		self.std = array.std()
		self.mean = array.mean()
		for g in gazetteers:
			references = self.get_references_for_gazetteer(g)
			for reference in references:
				#print "[II]   Updating distance of %s to %s km" % (reference.reference, g.distance.km)
				reference.distance = g.distance.km
				reference.deviation = abs(g.distance.km - self.std)

	
	def get_reference(self, article_reference):
		""" Returns the reference to the article reference, None if it doesn't exist
		"""
		for reference in self.references:
			if article_reference.article == reference.article and article_reference.sentence_number == reference.sentence_number and article_reference.position_in_sentence == reference.position_in_sentence and article_reference.location == reference.location:
				return reference
		return None

	def get_reference_by_id(self, article_reference_id):
		""" Returns the reference for the given id
		"""
		for reference in self.references:
			if reference.pk == article_reference_id:
				return reference
		return None
	
	def has_reference(self, article_reference):
		""" Checks if we have a reference to an article reference
		"""
		return self.get_reference(article_reference) is not None

	def is_reference_valid(self, article_reference):
		""" Return whether the reference is marked as valid
		"""
		if self.has_reference(article_reference):
			return self.get_reference(article_reference).is_valid()
		return False
	
	def get_reference_count(self):
		""" Get the number of references on this object
		"""
		count = 0
		for reference in self.references:
			count = count + 1
		return count
	
	def score(self, article):
		""" Returns the (precision, accuracy) tuple
		"""
		print "-" * 80
		print "[II] Scoring article: %s ID=%s" % (article, article.pk)
		article_references = article.article_references.all()
		total_references = len([article_reference for article_reference in article_references if article_reference.valid ])
		references_found = self.get_reference_count()
		print "[II]  Article %s has %s confirmed references, search found %s references" % (article.title, total_references, references_found)
		#print "[II]  Found references: "
		#for reference in self.references:
		#	print "\t%s" % reference
		#print "[II]  Article references: "
		#for article_reference in article_references:
		#	print "\t%s" % article_reference

		found = 0
		correct = 0
		for article_reference in article_references:
			reference = self.get_reference(article_reference)
			if reference:
				found = found + 1
				if article_reference.valid == self.is_reference_valid(article_reference):
					correct = correct + 1
				else:
					print "[II]   - Incorrect reference identified: %s (scored %s) ... %s" % \
												(reference, reference.weighting, reference.sentence)
			else:
				if article_reference.valid:
					print "[WW]  Reference missing for: %s" % article_reference
		
		precision = correct / float(total_references) if total_references > 0 else 0
		accuracy = correct / float(found) if found > 0 else 0

		print "[II] Score: Precision: %s, Accuracy: %s" % (precision, accuracy)
		print "-" * 80
		print

		return (precision, accuracy)


class Gazetteer(models.Model):
	name = models.CharField(max_length=255)
	parish = models.CharField(max_length=255, blank=True, null=True)
	level = models.PositiveIntegerField(default=3)
	weighting = models.PositiveIntegerField(default=0)
	point = models.PointField()

	objects = models.GeoManager()

	def __unicode__(self):
		if self.parish:
			return "%s, %s" % (self.name, self.parish)
		return self.name

	@staticmethod
	def load_data(shp_file, level=0, weighting=0, col_name="name", parish_name=None):
		if os.path.exists(shp_file):
			ds = DataSource(shp_file)
			layer = ds[0] if ds.layer_count else None
			Gazetteer.objects.filter(level=level).delete() # clear this level
			if layer and layer.num_feat:
				for feat in layer:
					geom = feat.geom.geos
					point = geom.centroid
					name = feat.get(col_name)
					parish = None if parish_name is None else feat.get(parish_name)
					print "Creating Gazetteer entry for %s" % name
					centroid = geom.centroid
					ctx = {
						'name' : name,
						'level' : level,
						'point' : point
					}
					if parish:
						ctx.update({'parish' : parish})
					Gazetteer.objects.create(**ctx)
	
	@staticmethod
	def load():
		Gazetteer.objects.all().delete() # Delete all
		path = os.path.join(settings.PROJECT_ROOT, "data")
		# Load parish data...
		#Gazetteer.objects.create(name='Jamaica', level=0, weighting=80)
		Gazetteer.load_data("%s/jamaica_parishes_WGS84.shp" % path, level=1, weighting=40, col_name="PARISH")
		Gazetteer.load_data("%s/community.shp" % path, level=2, weighting=20, col_name="COMMUNITY", parish_name="PARISH")

	# Use these to load in data for country, parish and community
	# Gazetteer.objects.create(name='Jamaica', geom=GEOSGeometry('POINT (-77.5 18.25)'), level=0, weighting=80)

	@staticmethod
	def find_references(articles=None):
		""" Searches articles for references to Gazetteer entries and return article references. 
			This is a naive search that just checks for equality. These have to be 
			confirmed manually later.
		""" 
		article_references = []

		if not articles:
			articles = Article.objects.filter(reviewed=True) # TODO Change this back to refs=None
			total = articles.count()
		else:
			total = len(articles)
		
		locations = Gazetteer.objects.all()

		start = 0
		amount = 1000 # Loop through by "amount" many articles
		stop = min(amount, total)

		#print start, stop, amount, total

		while stop <= total:
			some_articles = articles[start:stop]
			print "[II] Find references in articles from %s to %s" % (start, stop)

			for article in some_articles:

				print "[II] Searching for references in %s" % article
				title = article.title
				title_words = get_ne_words(title)
				body = article.body
				sentences = sent_tokenize(body)

				for location in locations:
					name = location.name.strip().lower()
					if not name:  # ignore blank names
						continue

					# search for a name in the title...
					positions = [ position for (position, (value, tag, foo)) in enumerate(title_words) if value.lower() == name ]
					for position in positions:
						(article_reference, created) = ArticleReference.objects.get_or_create(article=article, 
							gazetteer=location, position=position, location="title")
						if created:
							print "[II]  Found reference to %s in title of %s" % (name, title)
						article_references.append(article_reference)
					
					# search for a name in the body..
					for sentence_number, sentence in enumerate(sentences):
						sentence_words = get_ne_words(sentence)
						for (word_number, (word, tag, foo)) in enumerate(sentence_words):
							if word.lower() == name:
								(article_reference, created) = ArticleReference.objects.get_or_create(article=article, 
									gazetteer=location, position=word_number, location="body", sentence_number=sentence_number)
								if created:
									print "[II]  Found reference to %s in body of %s" % (name, title)
								article_references.append(article_reference)
			print "[II] Found a total of %s article references" % len(article_references)
			start = stop + 1
			stop = stop + amount
			articles = None
		return article_references

import unicodedata, re

all_chars = (unichr(i) for i in xrange(0x110000))
control_chars = ''.join(c for c in all_chars if unicodedata.category(c) == 'Cc')
# or equivalently and much more efficiently
control_chars = ''.join(map(unichr, range(0,32) + range(127,160)))

control_char_re = re.compile('[%s]' % re.escape(control_chars))

def remove_control_chars(s):
	if not s:
		return None
	return control_char_re.sub('', s)

# Create your models here.
class TrainingSet(models.Model):
	articles = models.ManyToManyField("Article", blank=True, null=True, related_name="training_set")

	def add_article(self, article):
		self.articles.add(article)
		self.save()

class Article(models.Model):
	title = models.CharField(max_length=255)
	body = models.TextField()
	raw = models.TextField(blank=True, null=True)
	date = models.DateTimeField(blank=True, null=True)
	created_at = models.DateTimeField(auto_now_add=True)
	url = models.URLField()
	reviewed = models.BooleanField(default=False)

	@staticmethod
	def extract_references(article):
		""" This runs our algorithm to identify references to place names in the given articles
		"""
		print "=" * 80
		print "[II] Extracting references from %s ... ID = %s" % (article, article.pk)
		references = References()
		# First, do a naive search for references...
		for gazetteer in Gazetteer.objects.all():
			name = gazetteer.name
			level = gazetteer.level
			weighting = gazetteer.weighting
			point = gazetteer.point
			# Search in the body...
			for i in range(0, len(article.sentences)):
				sentence = article.sentences[i]
				position = ArticleReference.reference_in_sentence(name, sentence)
				reference = ArticleReference(sentence_number=i, position_in_sentence=position, gazetteer=gazetteer, article=article, location="body", valid=True)
				if position > -1:
					references.add_reference(reference, False)
		references.update_distances() # Update distances


		# Add marks if parents are mentioned in the article
		for reference in references.get_references_by_level(2): # loop over communities
			if reference.is_parent_in_article():
				reference.add_weight(PARISH_PRESENT_WEIGHTING)
		
		for reference in references.references:

			if not reference.is_common():
				#print "[II] + Common weighting passed for %s" % reference
				reference.add_weight(COMMON_WEIGHTING)
			else:
				print "[II] - Common weighting FAILED for %s" % reference


			if reference.is_cased_properly():
				#print "[II] + Case test passed for %s" % reference
				reference.add_weight(NOT_LOWER_CASED_WEIGHTING)
			else:
				print "[II] - Case test FAILED for %s" % reference

			if reference.no_near_pronouns():
				#print "[II] + No near pronouns passed for %s" % reference
				reference.add_weight(NO_NEAR_PRONOUN_WEIGHTING)
			else:
				print "[II] - No near pronouns FAILED for %s" % reference

			
			if reference.within_one_std():
				#print "[II] + One std test passed for %s" % reference
				reference.add_weight(WITHIN_ONE_STDEV_WEIGHTING)
			else:
				print "[II] - One std test FAILED for %s" % reference

			if reference.is_nltk_ne:
				#print "[II] + NLTK NE test passed for %s" % reference
				reference.add_weight(NLTK_NE_TAG_WEIGHTING)
			else:
				print "[II] - NLTK NE test FAILED for %s" % reference

		references.remove_failed_references()

		# Print the score
		(precision, accuracy) = references.score(article)
		#print "[II] Score for %s\n\tPrecision: %s, Score: %s" % (article.title, precision, accuracy)
		return (precision, accuracy)

	@staticmethod
	def get_random_articles(amount=50):
		""" Returns some articles that have not yet been reviewed
		"""
		articles = Article.objects.filter(reviewed=False)[:amount]
		return articles

	def has_valid_references(self):
		if self.article_references.filter(valid=True):
			return True
		return False

	def __unicode__(self):
		return self.title

	@property
	def words(self):
		all_words = []
		sentence_count = len(self.sentences)
		for sentence in range(sentence_count):
			all_words.extend(self.get_sentence_words(sentence))
		return all_words

	@property
	def sentences(self):
		return sent_tokenize(self.body)

	def get_sentence_words(self, sentence):
		""" Returns the words in a sentence
		"""
		return nltk.word_tokenize(self.sentences[sentence])

	@property
	def title_words(self):
		return sent_tokenize(self.title)

	def get_sentence(self, sentence):
		return self.sentences[sentence]
	
	def get_pos_words(self, sentence):
		""" Returns a POS tagged sentence
		"""
		return nltk.pos_tag(self.get_sentence_words(sentence))
	
	def ne_chunked_sentence(self, sentence):
		""" Returns the NE chunks for the sentence
		"""
		ne_chunks = nltk.ne_chunk(self.get_pos_words(sentence))
		result = []
		# Loop and extract
		for ne_chunk in ne_chunks:
			if hasattr(ne_chunk, 'node'):
				node = ne_chunk.node
				for (word, tag) in ne_chunk:
					result.append((word, tag, node))
			else:
				result.append((ne_chunk[0], ne_chunk[1], None))
		return result

	@staticmethod
	def save_gleaner_articles(start=15, stop=4500):
		l = range(start, stop)
		l.reverse()
		gc = GleanerCrawler()
		for i in l:
			link = Link(url="http://jamaica-gleaner.com/latest/article.php?id=%s" % i)
			url = URL(link.url)
			source = unicode(remove_control_chars(url.download()))
			try:
				gc.visit(link, source)
			except Exception as e:
				print e

	def close(self):
		self.reviewed = True
		self.save()

	@staticmethod
	def crawl_gleaner(limit=10):
		links = ["http://www.jamaica-gleaner.com"]
		# add the last visited url
		last_url = cache.get("gleaner_referrer", None)
		if last_url and last_url != links[0]:
			print "[II] Will revisit %s first" % last_url
			links = [last_url] + links
		domains = ["jamaica-gleaner.com"]
		spider = GleanerCrawler(links=links, domains=domains)
		spider.run_crawl(limit=limit)

	@staticmethod
	def crawl_observer(limit=10):
		links = ["http://www.jamaicaobserver.com"]
		# add the last visited url
		last_url = cache.get("observer_referrer", None)
		if last_url and last_url != links[0]:
			print "[II] Will revisit %s first" % last_url
			links = [last_url] + links
		domains = ["jamaicaobserver.com"] 
		spider = ObserverCrawler(links=links, domains=domains)
		spider.run_crawl(limit=limit)
	

class ArticleReference(models.Model):
	LOCATIONS = (
		("title", "Title"),
		("body", "Body"),
	)
	article = models.ForeignKey(Article, related_name="article_references")
	gazetteer = models.ForeignKey(Gazetteer)
	location = models.CharField(max_length=10, choices=LOCATIONS)
	position = models.PositiveIntegerField() # position in text
	confirmed = models.BooleanField(default=False)
	valid = models.BooleanField(default=False)
	sentence_number = models.PositiveIntegerField(default=0)
	position_in_sentence = models.PositiveIntegerField(default=0)


	def extract_features(self):
		features = {
			PARISH_PRESENT : self.is_parent_in_article(),
			NOT_LOWER_CASED : self.is_cased_properly(),
			NO_NEAR_PRONOUN : self.no_near_pronouns(),
			WITHIN_ONE_STDEV : self.within_one_std(),
			HAS_COMMON_PREFIX : self.has_common_prefix(),
			NLTK_NE : self.is_nltk_ne
		}
		return features

	def evaluate(self, test):
		# check for references 
		if not hasattr(self, "references"):
			raise Exception("No references attrib attached to %s! Cannot evaluate" % self)
		# check for gazetteer
		if not self.gazetteer:
			raise Exception("This reference has no gazetteer object attached!")

		if test in TESTS:
			if not hasattr(self, "results"):
				self.results = {}
				for test_ in TESTS:
					self.results[test_] = False

			if test == COMMON:
				result = self.is_common()
			elif test == PARISH_PRESENT:
				result = self.is_parent_in_article()
			elif test == NOT_LOWER_CASED:
				result = self.is_cased_properly()
			elif test == NO_NEAR_PRONOUN:
				result = self.no_near_pronouns()
			elif test == WITHIN_ONE_STDEV:
				result = self.within_one_std()
			elif test == NLTK_NE:
				result = self.is_nltk_ne
			elif test == HAS_COMMON_PREFIX:
				result = self.has_common_prefix()
			else:
				raise Exception("No clause added for test: %s in reference.evaluate" % test)
			self.results[test] = result
			return result
		else:
			raise Exception("Unknown test %s" % test)

	@staticmethod
	def get_reference():
		""" Gets a reviewed reference
		"""
		return ArticleReference.objects.filter(confirmed=True).latest('pk')

	def get_ne_words_after(self, amount=3):
		""" Returns amoutn words after our reference word
		"""
		ne_words = self.ne_sentence_words
		start = self.position_in_sentence + self.reference_word_count
		end = start + amount
		return ne_words[start:end]

	def get_words_after(self, amount=3):
		""" Returns amoutn words after our reference word
		"""
		ne_words = self.sentence_words
		start = self.position_in_sentence + self.reference_word_count
		end = start + amount
		return ne_words[start:end]

	def get_ne_words_before(self, amount=3):
		""" Returns amount words before our reference word
		""" 
		sentence_words = self.ne_sentence_words
		start = self.position_in_sentence - amount
		end = self.position_in_sentence
		result = sentence_words[start:end]
		result.reverse()
		return result

	def get_words_before(self, amount=3):
		""" Returns amount words before our reference word
		""" 
		sentence_words = self.sentence_words
		start = self.position_in_sentence - amount
		end = self.position_in_sentence
		result = sentence_words[start:end]
		result.reverse()
		return result

	@property
	def word_before(self):
		words = self.get_words_before(amount=1)
		if words:
			return words[0]
		return None

	def has_common_prefix(self):
		""" Returns true if the word that comes before is our list 
			of common words that precede valid reference
		"""
		if self.word_before:
			return self.word_before.lower() in COMMON_PREFIXES[:30]

	@property
	def word_after(self):
		words = self.get_words_after(amount=1)
		if words:
			return words[0]
		return None

	@property
	def ne_word_before(self):
		words = self.get_ne_words_before(amount=1)
		if words:
			return words[0]
		return None

	@property
	def ne_word_after(self):
		words = self.get_ne_words_after(amount=1)
		if words:
			return words[0]
		return None


	@property
	def sentence_words(self):
		""" Returns the words in the sentence containing the reference
		"""
		sentence = self.sentence
		return nltk.word_tokenize(sentence)
	
	@property
	def ne_sentence_words(self):
		return self.article.ne_chunked_sentence(self.sentence_number)
	
	@property
	def reference_words(self):
		""" Returns the words in the reference (gazetteer)
		"""
		return nltk.word_tokenize(self.gazetteer.name)
	
	@property
	def pos_reference_words(self):
		return nltk.pos_tag(self.reference_words)

	@property
	def ne_reference_words(self):
		""" Returns the NE chunks for the sentence
		"""
		ne_chunks = nltk.ne_chunk(self.pos_reference_words)
		result = []
		# Loop and extract
		for ne_chunk in ne_chunks:
			if hasattr(ne_chunk, 'node'):
				node = ne_chunk.node
				for (word, tag) in ne_chunk:
					result.append((word, tag, node))
			else:
				result.append((ne_chunk[0], ne_chunk[1], None))
		return result
	
	@property
	def reference(self):
		return self.gazetteer.name

	@property
	def is_nltk_ne(self):
		""" Returns true if this is tagged a named entity by NLTK
		"""
		(word, tag, ne) = self.ne_sentence_words[self.position_in_sentence]
		return ne is not None
	
	@property
	def parent(self):
		parish = Gazetteer.objects.filter(level=1, name=self.gazetteer.parish)
		return parish

	@property
	def parent_in_article(self):
		return self.article.article_references.filter(gazetteer=self.parent)

	@property
	def reference_length(self):
		return len(self.gazetteer.name)

	@property
	def reference_word_count(self):
		return len(self.reference_words)
	
	@property
	def sentence(self):
		if self.location == "title":
			return self.article.title
		else:
			sentences = sent_tokenize(self.article.body)
			return sentences[self.sentence_number]

	def update_sentence_information(self):
		""" Fills in the details about what sentence the reference falls in and
			what position the reference is in the sentence
		"""
		if self.location == "title":
			position_in_title = ArticleReference.reference_in_sentence(self.reference, self.article.title)
			if position_in_title > -1:
				self.position_in_sentence = position_in_title
				self.save()
			else:
				print "[EE] Could not find proper reference to %s in title: %s" % (self.reference, self.article.title)
		else:
			body = self.article.body
			sentences = self.article.sentences
			index = 0 # keep track of how far we've gone
			reference = self.gazetteer.name
			print "[II] Trying to locate %s at position %s" % (reference, self.position)

			for i in range(0, len(sentences)):
				sentence = sentences[i]
				index = index + len(sentence) # Add the length of the sentence
				print "[II] Processing sentence: %s (ends at %s) ==> \"%s\"" % (i, index, sentence)
				if index >= self.position:
					# break this sentence into words
					position_in_sentence = ArticleReference.reference_in_sentence(reference, sentence)
					if position_in_sentence > -1:
						self.position_in_sentence = position_in_sentence
						self.sentence_number = i
						self.save()
					else:
						before = i - 1
						print "Could not find %s in sentence... checking the first non-empty sentence before: %s" % (reference, sentences[before])
						while before > 0 and len(sentences[before]) == 0:
							before = before - 1

						position_in_sentence = ArticleReference.reference_in_sentence(reference, sentences[before])
						if position_in_sentence > -1:
							self.position_in_sentence = position_in_sentence
							self.sentence_number = before
							print "[II] Updated position to sentence %s, position %s" % (self.sentence_number, self.position_in_sentence)
							self.save()
					break

	@staticmethod
	def find_incorrect_sentence_information(location="body"):
		references = ArticleReference.objects.filter(confirmed=True, location=location)
		def f(str):
			return str.lower()

		incorrect_references = []
		for reference in references:
			if map(f,reference.sentence_words[reference.position_in_sentence:reference.position_in_sentence + len(reference.reference_words)]) != map(f,reference.reference_words):
				incorrect_references.append(reference)
		print "%s incorrect references found" % len(incorrect_references)
		return incorrect_references
	
	def is_cased_properly(self):
		""" Checks if the reference is either title or upper cased
		"""
		sentence = self.sentence
		reference = self.gazetteer.name
		lower_pos = ArticleReference.reference_in_sentence(reference, sentence)
		upper_pos = ArticleReference.reference_in_sentence(reference, sentence, comparison="upper")
		title_pos = ArticleReference.reference_in_sentence(reference, sentence, comparison="title")
		return upper_pos == lower_pos or title_pos == lower_pos

	def followed_by_words(self, words):
		amount =  len(words)
		words_after = self.get_words_after(amount=amount)
		return words_after == words

	def followed_by_ne(self):
		return self.ne_word_after

	def preceded_by_ne(self):
		return self.ne_word_before

	@property
	def followed_by_apos(self):
		return self.word_after == "'s"

	def is_part_of_a_reference(self):
		""" Returns true if our word is a part of another reference. For example
			"Kingston" in "New Kingston". Kingston is a part of the New Kingston 
			reference.
		"""
		for reference in self.references:
			if reference == self or self.position_in_sentence == reference.position_in_sentence:
				continue
			if reference.sentence == self.sentence:
				my_start_index = self.position_in_sentence
				my_end_index = my_start_index + self.reference_word_count
				word_start_index = reference.position_in_sentence
				word_end_index = word_start_index + reference.reference_word_count

				if my_start_index >= word_start_index and my_end_index <= word_end_index:
					return True
		return False

	def is_part_of_ne(self):
		""" Returns true if our reference word is apart of a named entity
		"""
		if self.ne_word_before:
			return self.ne_word_before[1] in ["NP", "NNP"]
		if self.ne_word_after:
			return self.ne_word_after[1] in ["NP", "NNP"]

	def reference_exists_at(self, position, sentence_number=None):
		if sentence_number:
			sentence = self.get_sentence(sentence_number)
		else:
			sentence = self.sentence
		for reference in self.references:
			if reference.sentence == sentence:
				return reference.position_in_sentence == position
		return False

	def no_near_pronouns(self):
		""" Returns true if no proper nouns follow or precede the reference
		"""
		ne_words = self.ne_sentence_words
		ne_reference_words = self.ne_reference_words
		ref_word_count = len(ne_reference_words)

		ne_word_after = self.ne_word_after
		ne_word_before = self.ne_word_before

		# Keep track of some variables
		followed_by_reference = self.followed_by_reference()
		preceded_by_reference = self.preceded_by_reference()
		followed_by_apos = self.followed_by_apos
		followed_by_ne = ne_word_after		
		preceded_by_ne = ne_word_before
		word_after = self.word_after
		word_before = self.word_before

		word_after_title_cased = is_title_cased(word_after)
		word_before_title_cased = is_title_cased(word_before)

		#print " NE Before: %s, After: %s" % (ne_word_before, ne_word_after)
		#print " Reference before?: %s, Reference after? %s" % (self.preceded_by_reference(), 
		#	self.followed_by_reference())

		if word_after_title_cased and not followed_by_reference:
			if ne_word_after[1] not in ["DT", "IN"]:
				#print "%s comes after, is title cased and it's not a reference" % word_after
				return False

		if word_before_title_cased and not preceded_by_reference:
			if ne_word_before[1] not in ["DT", "IN"]:
				#print "%s comes before, is title cased and it's not a reference" % word_before
				return False

		# Apostrophe testing...
		if followed_by_apos:
			# Get the word after the apos
			ne_word_after_apos = self.get_ne_words_after(2)[1:][0]
			(word, pos_tag, ne_tag) = ne_word_after_apos
			if is_title_cased(word) and not ne_tag and pos_tag in ["NNP", "NP"]:
				#print " %s (%s, %s) follows as a titled cased, non-NE word" % (word, pos_tag, ne_tag)
				return False

		# If NLTK thinks the word is ORGANIZATION and we are followed by 'of the'
		if reduce(operator.and_, [ ne_reference_word[2] == "ORGANIZATION" for \
			ne_reference_word in ne_reference_words ]):
			if self.followed_by_words(["of", "the"]):
				#print " The words \"of the\" follow our reference... this can't be valid"
				return False
			if self.followed_by_words(["of"]):
				if not self.reference_exists_at(self.position_in_sentence + \
					self.reference_word_count + 1):
					# examine the word more carefully... its not a reference...
					ne_word = self.get_ne_words_after(2)[1:][0]
					(word, pos_tag, ne_tag) = ne_word
					if is_title_cased(word):
						#print " Our referenced is suffixed by \"of %s\", we think its not valid" % \
						#	(word)
						return False

		# If we are PART of a reference... nope nope nope... can't work...
		if self.is_part_of_a_reference():
			#print " Our word is part of a reference... this cannot be valid"
			return False


		if ne_word_after and not self.followed_by_reference():
			tag = ne_word_after[1]
			node = ne_word_after[2]
			if tag in ["NP", "NNP"] or node != None:
				#print " Word after %s is a pronoun and not a reference" % ne_word_after[0]
				pass

		if ne_word_before and not self.preceded_by_reference():
			tag = ne_word_before[1]
			node = ne_word_before[2]
			#print "Previous word is: %s - %s" % (str(previous_word), tag)
			if tag in ["NP", "NNP"] or node != None:
				#print " Word before %s is a pronoun and not a reference" % ne_word_before[]
				pass #return False
		return True

	def followed_by_reference(self):
		references = self.references.references
		for reference in references:
			if reference.sentence == self.sentence and \
					reference.position_in_sentence == self.position_in_sentence + self.reference_word_count:
				return True
		# Check for Jamaica
		if self.word_after and self.word_after.lower() == "jamaica":
			return True
		return False

	def preceded_by_reference(self):
		references = self.references.references
		ne_words = self.ne_sentence_words

		for reference in references:
			if reference.sentence == self.sentence and \
					reference.position_in_sentence == self.position_in_sentence - 1:
				return True
		# Check for Jamaica
		if self.word_before and self.word_before.lower() == "jamaica":
			return True
		return False
	
	def within_one_std(self):
		""" Returns true if this reference is within one std of the mean
		"""
		if hasattr(self, 'references'):
			return self.deviation <= abs(self.references.std - self.references.mean)
		else:
			raise Exception("No references object associated with this ArticleReference")

	@staticmethod
	def reference_in_sentence(reference, sentence, comparison="lower"):
		""" Finds the position of the reference in a sentence. Consider the special case
			where the part of the reference may have been joined to another word by the tokenizer
			because a dash was used. Example "The Kingston-Ochio Rios chapter
		"""
		if comparison == "lower":
			sentence = sentence.lower()
			reference = reference.lower()
		elif comparison == "title":
			sentence = sentence.title()
			reference = reference.title()
		elif comparison == "upper":
			sentence = sentence.upper()
			reference = reference.upper()

		sentence_words = nltk.word_tokenize(sentence)
		reference_words = nltk.word_tokenize(reference)
		ref_word_count = len(reference_words)

		for i in range(0, len(sentence_words)):
			complete_reference_match = reference_words == sentence_words[i:i+ref_word_count]
			partial_match = False
			if len(reference_words) > 1:
				partial_match = sentence_words[i].endswith(reference_words[0]) and sentence_words[i+1:i+ref_word_count] == reference_words[1:]
				if not partial_match and len(sentence_words) > (i + ref_word_count):
					# check for endings....
					last_reference_word_in_sentence = sentence_words[i+ref_word_count-1]
					last_reference_word = reference_words[ref_word_count-1]
					partial_match = last_reference_word_in_sentence.startswith(last_reference_word) and sentence_words[i:i+ref_word_count-1] == reference_words[:ref_word_count-1]
			if complete_reference_match:
				#print "[II] Found reference %s in sentence %s at position %s" % (reference, sentence, i)
				return i
			elif partial_match:
				#print "[II] Found reference %s in sentence %s at position %s" % (reference, sentence, i-1)
				return i
		return -1
	

	def __unicode__(self):
		valid = "valid" if self.valid else "invalid"
		return "%s found in sentence %s, position %s in %s (%s)" % (self.gazetteer.name, self.sentence_number, self.position_in_sentence, self.location, valid)

	def get_sentence(self):
		""" Returns the sentence that the reference is contained in
		"""
		if self.location == "title":
			return 0
		else:
			sentences = article.sentences

	@property
	def reference_context(self):
		location = self.location
		content = self.article.title if location == "title" else self.article.body
		position = self.position
		reference_text = self.gazetteer.name.upper()
		reference_length = len(self.gazetteer.name)
		return "%s<b>%s</b>%s" % (content[:position], reference_text, content[(position+reference_length):])

	@property
	def description(self):
		""" Returns surrounding text to go along side the reference to provide some context
		"""
		name = self.gazetteer.name
		title = self.article.title
		html = "<b class='gazetteer-reference'>" + name + "</b>"
		if self.location == "title":
			return title[:self.position] + html + title[self.position + len(name):]
		else:
			body = self.article.body
			start_index = max(0, self.position - 100) # start a couple words before...
			start_dots = "... " if start_index else ""
			end_index = min(len(body), (self.position + len(name) + 100))
			end_dots = " ..." if end_index < len(body) else ""
			return start_dots + body[start_index:self.position] + html + body[self.position + len(name) : end_index] + end_dots

	def add_weight(self, weighting):
		self.weighting = self.weighting + weighting

	def sub_weight(self, weighting):
		self.weighting = self.weighting - weighting

	def scale_weight(self, scale):
		if scale >= 0:
			self.weighting = self.weighting * scale
		else:
			self.weigthing = self.weighting / scale

	def get_centroid(self):
		return self.gazetteer.point

	def is_valid(self):
		return self.valid
	
	def set_valid(self, valid):
		self.valid = valid
	
	def get_parent(self):
		""" Gets the parent gazetteer
		"""
		return Gazetteer.objects.get(level=1, name=self.gazetteer.parish)
	
	def get_parent_weight(self):
		return self.get_parent().weight

	def is_parent_in_article(self):
		""" Returns true if a community's parish is mentioned in the article
		"""
		occurrences = 0
		if self.gazetteer.level == 1:
			return False
		else:
			if self.gazetteer.parish.startswith("St"):
				parish_names = [self.gazetteer.parish]
				if self.gazetteer.parish.startswith("St. "):
					parish_names.append(self.gazetteer.parish.replace("St. ", "St "))
				else:
					parish_names.append(self.gazetteer.parish.replace("St ", "St. "))
				print "Will filter for %s" % parish_names
				parishes = Gazetteer.objects.filter(level=1, name__in=parish_names)
				for parish in parishes:
					occurrences += self.references.get_occurrences(parish)
				return occurrences > 0
			else:
				try:
					parish = Gazetteer.objects.get(level=1, name=self.gazetteer.parish)
				except Gazetteer.DoesNotExist:
					return False
				return self.references.get_occurrences(parish) > 0

	def is_common(self):
		return self.gazetteer.name.lower() in COMMON_WORDS


class GleanerCrawler(Spider):
	site = "gleaner"
	limit = 10
	parsed = 0
	articles = []
	base_url  = ""
	article_classes = [
		# Article classes... header class, body class
		("h1.news-story-header", "div.KonaBody"),
		("h2.news-story-header", "div.KonaBody"),
	]

	def is_article(self, link):
		if re.search("\#[a-z_0-9]+$",link.url): # ignore hashed locations
			return False

		if "article.php" in link.url:
			return True
		if re.search("lead[0-9]+\.html", link.url):
			return True
		if re.search("news[0-9]+\.html", link.url):
			return True
		return False

	def priority(self, link, method=DEPTH):
		p = 0.0
		if self.is_article(link):
			p = 1.0
		elif link.url.endswith("latest") or link.url.endswith("lead/") or link.url.endswith("news/"):
			p = 0.7
		return p


	def follow(self, link):
		result = link.url.startswith("http://jamaica-gleaner") or link.url.startswith("http://www.jamaica-gleaner")
		return result

	def visit(self, link, source=None):
		time = datetime.datetime.today().strftime("%H:%M")
		print "[II] Visited %s at %s COMING FROM %s" % (link.url, time, link.referrer)
		cache.set("%s_referrer" % self.site, link.referrer) 

		if source:
			# Find the article title and body...
			e = Element(source)
			article_found  = False
			for (title_class, body_class) in self.article_classes:
				bodies = e.by_tag(body_class)
				titles = e.by_tag(title_class)

				if bodies and titles:
					article_found = True
					title = plaintext(titles[0].source)
					body = plaintext(bodies[0].source)

					(article, created) = Article.objects.get_or_create(title=title, body=body, url=link.url)
					count = Article.objects.count()
					if created:
						self.articles.append(article)
						# Also save the raw source
						article.raw = source
						article.save()
						print "[II]  + Article created for: %s from %s (%s articles now, time is %s)" % (title, link.url, count, time)
					else:
						print "[II]  - Article %s already exists (%s articles now, time is %s)" % (title, count, time)
			if not article_found:
				#print "[WW] No article on this page: %s" % link.url
				pass
		else:
			#print "[WW] No source for: %s" % link.url
			pass

	def run_crawl(self, limit=10000):
		print "[II] Starting crawler (will stop after %s article(s))" % limit
		while not self.done or len(self.articles) < limit:
			if self.done:
				print "[II] Quiting... sorry.. all done"
				return
			#print "[II] Crawling again %s" % self.visited
			try:
				self.crawl(method=DEPTH, cached=False, throttle=10, delay=15)
			except Exception as e:
				print "[EE] Error occurred: %s" % e
		print "Saved %s article(s)" % len(self.articles)
		return self.articles



class ObserverCrawler(GleanerCrawler):
	site = "observer"
	limit = 10
	parsed = 0
	articles = []
	base_url  = ""
	article_classes = [
		# Article classes... header class, body class
		("title", "div#story_body"),
	]

	def is_article(self, link):
		if "/news/" in link.url and not link.url.endswith("/news/"):
			return True
		return False

	def priority(self, link, method=DEPTH):
		p = 0.0
		if self.is_article(link):
			p = 1.0
		elif not link.url.endswith("/news/") and "/news/" in link.url:
			p = 0.7
		return p


	def follow(self, link):
		result = link.url.startswith("http://www.jamaicaobserver.com")
		return result
	

#@receiver(post_save)
def article_created(sender, instance, **kwargs):
	pass
	id = instance.pk
	title = instance.title
	ctx = {"id":id, "title":title}
	try:
		print "[II] Broadcasting message about creation of: %s" % title
		from django_socketio.clients import CLIENTS
		print CLIENTS
		broadcast_channel(ctx, channel="articles")
		#broadcast(ctx)
	except NoSocket as e:
		print "No sockets to send broadcast to :( ... %s" % e
	
def get_common_words():
	data = open("%s/data/common_english_words.txt" % settings.PROJECT_ROOT).read()
	words = data.splitlines()
	return words
COMMON_WORDS = get_common_words()

def get_common_prefixes():
	data = open("%s/data/words_before.txt" % settings.PROJECT_ROOT).read()
	words = data.splitlines()
	return words
COMMON_PREFIXES = get_common_prefixes()

def get_popular_names():
	""" Get popular jamaican names
	"""
	data = open("%s/data/popular_names.txt" % settings.PROJECT_ROOT).read().lower()
	names = data.splitlines()
	names.sort()
	return names

def is_title_cased(word):
	if not word:
		return False
	if not re.findall("[a-z]",word):
		return False
	return word.title() == word

def get_sentence_for(article_reference_id):
	try:
		ref = ArticleReference.objects.get(pk=article_reference_id)
		return ref.sentence
	except ArticleReference.DoesNotExist:
		return None

def get_reference(article_reference_id):
	try:
		refs = References.from_article_reference_id(article_reference_id)
		return refs.get_reference_by_id(article_reference_id)
	except ArticleReference.DoesNotExist:
		return None

def get_ne_words(str):
	pos_words = nltk.pos_tag(nltk.word_tokenize(str))
	ne_chunks = nltk.ne_chunk(pos_words)
	result = []
	# Loop and extract
	for ne_chunk in ne_chunks:
		if hasattr(ne_chunk, 'node'):
			node = ne_chunk.node
			for (word, tag) in ne_chunk:
				result.append((word, tag, node))
		else:
			result.append((ne_chunk[0], ne_chunk[1], None))
	return result
