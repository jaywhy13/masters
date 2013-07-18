import os

from django.core.management.base import BaseCommand, CommandError
from django.core.management import call_command
from django.conf import settings


from nltk import FreqDist
from optparse import make_option

from masters.articles.models import *
from masters.articles.models import TESTS

class Command(BaseCommand):
    args = ''
    help = 'Returns stats'

    option_list = BaseCommand.option_list + (
        make_option('--references',
            action='store',
            dest='references',
            default=None,
            help=''),
        make_option('--test',
            action='store',
            dest='test',
            default=None,
            help=''),
    )


    def handle(self, *args, **options):
    	""" 
    	Tests a reference
    	"""
        references = options["references"]
        test = options["test"]
        if not test:
            tests = TESTS
        else:
            tests = [test]

        if not references:
            references = ArticleReference.objects.filter(valid=True, confirmed=True)
        else:
            reference_ids = references.split(",")
            references = ArticleReference.objects.filter(pk__in=reference_ids)

        for reference in references:
            refs = References(reference.article.article_references.all())
            for ref in refs:
                if ref.pk == reference.pk:
                    print "%s == Sentence: %s" % (ref.pk, ref.sentence)
                    for test in tests:
                        result = "passes" if ref.evaluate(test) else "fails"
                        print "==> TEST RESULT: %s - %s %s %s" % (ref.pk, ref, result, test)
                    break




