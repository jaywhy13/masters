from django.db import models
from pattern.web import Spider, BREADTH, DEPTH, plaintext, Element
import re

# Create your models here.
class Article(models.Model):
	title = models.CharField(max_length=255)
	body = models.TextField()
	date = models.DateTimeField(blank=True, null=True)
	created_at = models.DateTimeField(auto_now_add=True)
	url = models.URLField()

	@staticmethod
	def crawl_gleaner(url, limit=10):
		links = ["http://www.jamaica-gleaner.com/"]
		spider = GleanerCrawler(links=links)
		spider.run_crawl()

class GleanerCrawler(Spider):

	limit = 10
	parsed = 0
	articles = []

	def follow(self, link):
		if re.search("\#[a-z_0-9]+$",link.url): # ignore hashed locations
			return False

		if "article.php" in link.url:
			return True
		elif re.search("lead[0-9]+\.html", link.url):
			return True
		return False
	
	def visit(self, link, source=None):
		print "[II] Visited %s" % link.url
		self.parsed += 1
		if source:
			# Find the article title and body...
			e = Element(source)
			bodies = e.by_tag("div.KonaBody")
			titles = e.by_tag("h1.news-story-header")

			if bodies and titles:
				title = plaintext(titles[0].source)
				body = plaintext(bodies[0].source)

				print "[II]  + Creating article: %s from %s" % (title, link.url)
				article = Article.objects.get_or_create(title=title, body=body, url=link.url)
				self.articles.append(article)
		else:
			print "[WW] No source for: %s" % link.url

	def run_crawl(self, limit=10):
		print "[II] Starting crawler"
		while not self.done or self.parsed < limit:
			self.crawl(method=BREADTH, cached=False, throttle=5, delay=5)
		return self.articles



