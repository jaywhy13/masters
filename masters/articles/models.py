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

class Gazetteer(models.Model):
	name = models.CharField(max_length=255)
	parish = models.CharField(max_length=255, blank=True, null=True)
	level = models.PositiveIntegerField(default=3)
	weighting = models.PositiveIntegerField(default=0)
	point = models.PointField()

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
	def refine_references():
		total = ArticleReference.objects.count()
		start = 0
		amount = 1000
		stop = min(amount, total)
		refined = 0
		reference_ids = []

		while stop < total:

			print "[II] Refining references between %s and %s" % (start, stop)
			if refined:
				import time
				print "[II] %s article references refined thus far" % refined
				print


			article_references = ArticleReference.objects.all()[start:stop]
			reference_ids = []
			for article_reference in article_references:
				article = article_reference.article
				gazetteer = article_reference.gazetteer
				position = article_reference.position
				content = article.body if article_reference.location == "body" else article.title

				start = max(0, position - 50)
				end = min(len(content), position + len(gazetteer.name) + 50)

				# Do a title case comparison
				context = content[start:end].replace("\n","")

				# Check if it's a word boundary

				if not Gazetteer.is_valid_reference(gazetteer.name, position, content):
					print "[II] Removing non-title-cased reference to **%s** in %s of %s\n\tContext: %s" % (gazetteer.name.title(), article_reference.location, article.title, context)
					refined += 1
					reference_ids.append(article_reference.pk)
			if reference_ids:
				ArticleReference.objects.filter(pk__in=reference_ids).delete()
			start = stop + 1
			stop = stop + amount
		print "[II] Refined %s articles in total" % refined

	@staticmethod
	def is_valid_reference(name, position, content):
		start = max(0, position - 2)
		end = min(len(content), position + len(name) + 2)
		context = content[start:end].replace("\n","")
		word_in_context = content[position:len(name) + position]
		# Check if it's a word boundary
		start = max(0, position - 2)
		end = min(len(content), position + len(name) + 2)
		boundary_context = content[start:end]

		start = max(0, position - 10)
		stop = min(len(content), position + len(name) + 10) 
		wide_context = content[start:end]

		is_word_boundary = re.search(r"\b%s\b" % name, boundary_context, re.I)
		is_title_cased = name.title() == word_in_context
		return is_word_boundary and is_title_cased

	@staticmethod
	def find_references(articles=None):
		""" Searches articles for references to Gazetteer entries and return article references
		""" 
		article_references = []

		if not articles:
			articles = Article.objects.filter(article_references=None)
			total = articles.count()
		else:
			total = len(articles)
		
		locations = Gazetteer.objects.all()

		start = 0
		amount = 1000 # Loop through by "amount" many articles
		stop = min(amount, total)

		while stop < total:
			some_articles = articles[start:stop]
			print "[II] Find references in articles from %s to %s" % (start, stop)

			for article in some_articles:
				if not batch_mode:
					print "[II] Searching for references in %s" % article
				title = article.title.lower()
				body = article.body.lower()
				for location in locations:
					name = location.name.strip().lower()
					if not name:  # ignore blank names
						continue

					# search for a name in the title...
					position = title.find(name)
					while position > -1:
						if Gazetteer.is_valid_reference(name, position, article.title):
							(article_reference, created) = ArticleReference.objects.get_or_create(article=article, 
								gazetteer=location, position=position, location="title")
							if created:
								print "[II] Found refence to %s in title of %s" % (name, title)
						position = title.find(name, position+1)
						article_references.append(article_reference)
					
					# search for a name in the body..
					position = body.find(name)
					while position > -1:
						if Gazetteer.is_valid_reference(name, position, article.body):
							(article_reference, created) = ArticleReference.objects.get_or_create(article=article, 
								gazetteer=location, position=position, location="body")
							if created:
								print "[II] Found refence to %s in body of %s" % (name, title)
						position = body.find(name, position+1)
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
    return control_char_re.sub('', s)

# Create your models here.
class Article(models.Model):
	title = models.CharField(max_length=255)
	body = models.TextField()
	raw = models.TextField(blank=True, null=True)
	date = models.DateTimeField(blank=True, null=True)
	created_at = models.DateTimeField(auto_now_add=True)
	url = models.URLField()
	reviewed = models.BooleanField(default=False)

	def __unicode__(self):
		return self.title

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

	def get_words_after(self, amount=3):
		""" Returns amoutn words after our reference word
		"""
		sentence_words = self.sentence_words
		start = self.position_in_sentence + 1
		end = start + amount
		return sentence_words[start:end]
	
	def get_words_before(self, amount=3):
		""" Returns amount words before our reference word
		""" 
		sentence_words = self.sentence_words
		start = self.position_in_sentence - amount
		end = self.position_in_sentence - 1
		return sentence_words[start:end]

	@property
	def sentence_words(self):
		""" Returns the words in the sentence containing the reference
		"""
		sentence = self.sentence
		return nltk.word_tokenize(sentence)
	
	@property
	def reference_words(self):
		""" Returns the words in the reference (gazetteer)
		"""
		return nltk.word_tokenize(self.gazetteer.name)
	
	@property
	def reference(self):
		return self.gazetteer.name

	@property
	def reference_length(self):
		return len(self.gazetteer.name)
	
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

	@staticmethod
	def reference_in_sentence(reference, sentence):
		""" Finds the position of the reference in a sentence. Consider the special case
			where the part of the reference may have been joined to another word by the tokenizer
			because a dash was used. Example "The Kingston-Ochio Rios chapter
		"""
		sentence = sentence.lower()
		reference = reference.lower()

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
				print "[II] Found reference %s in sentence %s at position %s" % (reference, sentence, i)
				return i
			elif partial_match:
				print "[II] Found reference %s in sentence %s at position %s" % (reference, sentence, i-1)
				return i
		return -1

	def __unicode__(self):
		return "%s found at index %s in %s" % (self.gazetteer.name, self.position, self.location)

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
	



# Add a reference.get_sentence, reference.get_surronding_words, reference.get_pos_tagged 
# Use NLTK to examine POS of different types of occurrences
# Build a geo stop word list by virtue of occurrence
# Add method to get random x articles that haven't been reviewed
# Find references to Jamaica in the articles reviewed thus far
# Vary pass mark
# Find pass mark necessary to achieve F-measure of 0.8. 
# Vary weightings 
# Add sentence, sentence_number and position_in_sentence to reference. 
# Add a review_references page to check over references .... or just add Admin link
# Review references like "Kingston police division", "Kingston Police Division" and "Arnette Gardens Football team"
# Also review joined references like "Kingston and St Andrew"
# Find out how to review tagged locations in NLTK corpus
# Find popular surnames 
# Get NLTK classification of word by sentence, index
