import os

from django.core.management.base import BaseCommand, CommandError
from django.core.management import call_command
from django.conf import settings

from nltk import FreqDist

from masters.articles.models import *


class Command(BaseCommand):
    args = ''
    help = 'Returns stats'

    def handle(self, *args, **options):
    	""" 
    	Finds references
    	"""
    	# Select limit articles
        if args:
            limit = args[0]
        else:
            limit = 10000

        articles = Article.objects.filter(reviewed=True)[:limit]

        total = articles.count()
        skipped = 0
        ne_chunks = 0
        parents_in_article = 0
        total_references = 0
        total_deviation = 0
        one_std = 0
        total_avg_occurrences = 0
        total_common_references = 0
        max_references = 0
        min_references = 1000000
        no_near_pronouns = 0
        fdist = FreqDist()

        print "[II] Building stats... please wait..."
        for article in articles:
            print "[II] Processing: %s - %s" % (article.pk, article)
            article_references = article.article_references.filter(valid=True)
            references = References(article_references)
            count = article_references.count()
            max_references = max(count, max_references)
            min_references = min(count, min_references)
            total_references = total_references + count
            for article_reference in article_references:
                # Check if it is a NE chunk 
                if article_reference.is_nltk_ne:
                    ne_chunks = ne_chunks + 1
                # Check if parent in article
                if article_reference.gazetteer.level == 2 and article_reference.parent_in_article:
                    parents_in_article = parents_in_article + 1
                # Check if it's common
                if article_reference.is_common():
                    total_common_references = total_common_references + 1
                word_before = article_reference.get_words_before(amount=1)
                if word_before:
                    word_before = word_before[0]
                    fdist.inc(word_before.lower())
                if article_reference.no_near_pronouns():
                    no_near_pronouns += 1
                if article_reference.within_one_std():
                    one_std += 1

            # Add the std 
            total_deviation = total_deviation + references.std
            avg_reference_occurrences = sum(references.occurrences.values()) / float(count) if count > 0 else 0
            total_avg_occurrences = total_avg_occurrences + avg_reference_occurrences

        print "[II] Statistics: (Total, Avg)"
        print "\tTotal Articles: %s" % total
        print "\tTotal References: %s" % total_references
        print "\tAverage references per article: %s" % avg(total_references, total)
        print "\tMax/Min References: %s, %s" % (max_references, min_references)
        print "\tNamed Entity Chunks: %s approx %s" % (ne_chunks, percentage(ne_chunks,total_references))
        print "\tParents in article: %s approx %s " % (parents_in_article, percentage(parents_in_article, total_references))
        print "\tArticles within one std: %s" % avg(total_deviation, total_references)
        print "\tAverage Deviation: %s" % avg(total_deviation, total_references)
        print "\tAverage Occurrences: %s" % avg(total_avg_occurrences, total_references)
        print "\tAverage No Near Pronouns: %s" % avg(no_near_pronouns, total_references)
        print "\tTotal Common Occurrences: %s approx %s" % (total_common_references, percentage(total_common_references, total_references))
        print "\tMost common 20 before-words: %s" % ", ".join(fdist.keys())

        words_before_file = "%s/words_before.txt" % settings.PROJECT_ROOT
        try:
            os.remove(words_before_file)
        except Exception:
            pass
        with open(words_before_file, "a") as dest:
            dest.write("\n".join(fdist.keys()))
            dest.close()



def percentage(amount, total, decimal_places=2):
    if total == 0:
        return "0.0%"
    return "%s" % round((amount / float(total)) * 100, decimal_places) + "%"
          
def avg(amount, total, decimal_places=2):
    if total == 0:
        return 0.0
    return round((amount / float(total)) * 1, decimal_places)
