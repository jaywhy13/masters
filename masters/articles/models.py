from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver
from django_socketio import broadcast, broadcast_channel, NoSocket
from pattern.web import Spider, BREADTH, DEPTH, plaintext, Element
from django.contrib.gis.utils import LayerMapping
from django.contrib.gis.gdal import DataSource		
from django.contrib.gis.geos import GEOSGeometry
import re
import os

class Gazetteer(models.Model):
	name = models.CharField(max_length=255)
	parish = models.CharField(max_length=255, blank=True, null=True)
	level = models.PositiveIntegerField()\

	def __unicode__(str):
		return self.name

	@staticmethod
	def load_data(shp_file, level=0, weighting=0, col_name="name"):
		if os.path.exists(shp_file):
			ds = DataSource(shp_file)
			layer = ds[0] if ds.layer_count else None
			Gazetteer.objects.filter(level=level).delete() # clear this level
			if layer and layer.num_feat:
				for feat in layer:
					geom = feat.geom.geos
					name = feat.get(col_name)
					print "Creating Gazetteer entry for %s" % name
					centroid = geom.centroid
					Gazetteer.objects.create(name=name, level=level)

	# Use these to load in data for country, parish and community
	# Gazetteer.objects.create(name='Jamaica', geom=GEOSGeometry('POINT (-77.5 18.25)'), level=0, weighting=80)

	@staticmethod
	def find_references(articles=None):
		""" Searches articles for references to Gazetteer entries and return article references
		""" 
		if not articles:
			articles = Article.objects.all()
		
		locations = Gazetteer.objects.all()
		
		for article in articles:
			title = article.title.lower()
			body = article.body.lower()
			for location in locations:
				name = location.name.lower()
				# search for a name in the title...
				position = title.find(name)
				while position > -1:
					(article_reference, created) = ArticleReference.objects.get_or_create(article=article, 
						gazetteer=location, position=position, location="title")
					print "[II] Found refence to %s in title of %s" % (name, title)
					position = title.find(name, position+1)
				
				# search for a name in the body..
				position = body.find(name)
				while position > -1:
					(article_reference, created) = ArticleReference.objects.get_or_create(article=article, 
						gazetteer=location, position=position, location="body")
					print "[II] Found refence to %s in body of %s" % (name, title)
					position = body.find(name, position+1)

# Create your models here.
class Article(models.Model):
	title = models.CharField(max_length=255)
	body = models.TextField()
	raw = models.TextField()
	date = models.DateTimeField(blank=True, null=True)
	created_at = models.DateTimeField(auto_now_add=True)
	url = models.URLField()

	def __unicode__(self):
		return self.title

	@staticmethod
	def crawl_gleaner(limit=10):
		links = ["http://www.jamaica-gleaner.com"]
		domains = ["jamaica-gleaner.com"]
		spider = GleanerCrawler(links=links, domains=domains)
		spider.run_crawl(limit=limit)

class ArticleReference(models.Model):
	LOCATIONS = (
		("title", "Title"),
		("body", "Body"),
	)
	article = models.ForeignKey(Article)
	gazetteer = models.ForeignKey(Gazetteer)
	location = models.CharField(max_length=10, choices=LOCATIONS)
	position = models.PositiveIntegerField()
	confirmed = models.BooleanField(default=False)

class GleanerCrawler(Spider):

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
		print "[II] Visited %s COMING FROM %s" % (link.url, link.referrer)
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
						print "[II]  + Article created for: %s from %s (%s articles now)" % (title, link.url, count)
					else:
						print "[II]  - Article %s already exists (%s articles now)" % (title, count)
			if not article_found:
				#print "[WW] No article on this page: %s" % link.url
				pass
		else:
			#print "[WW] No source for: %s" % link.url
			pass

	def run_crawl(self, limit=10):
		print "[II] Starting crawler (will stop after %s article(s))" % limit
		while not self.done or len(self.articles) < limit:
			#print "[II] Crawling again %s" % self.visited
			self.crawl(method=DEPTH, cached=False, throttle=5, delay=5)
		print "Saved %s article(s)" % len(self.articles)
		return self.articles


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
	
