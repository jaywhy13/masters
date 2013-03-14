"""
This file demonstrates writing tests using the unittest module. These will pass
when you run "manage.py test".

Replace this with more appropriate tests for your application.
"""

from django.test import TestCase
from models import *

class Crawler(TestCase):

	def test_crawler(self):
		print "Testing article retrieval"
		articles = Article.crawl_gleaner("www.jamaica-gleaner.com")
		self.assertGreater(len(articles), 0)

