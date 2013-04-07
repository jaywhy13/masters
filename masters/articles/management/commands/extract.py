from django.core.management.base import BaseCommand, CommandError
from django.core.management import call_command
from django.conf import settings
from masters.articles.models import *
from optparse import make_option

class Command(BaseCommand):
    args = ''
    help = 'Executes our search algorithm'

    option_list = BaseCommand.option_list + (
        make_option('--limit',
            action='store',
            dest='limit',
            default=100,
            metavar="LIMIT",
            help='Extracts blah'),
        )

    def handle(self, *args, **options):
    	""" 
    	Finds references
    	"""
        ids = [ arg for arg in args ]

        limit = options["limit"]

    	# Select limit articles
        ctx = {
        "reviewed" : True,
        }
        if ids:
            ctx.update(dict(pk__in=ids))

        precision_values = []
        accuracy_values = []

    	articles = Article.objects.filter(**ctx).order_by("-pk")[:limit]
        count = 0
    	for article in articles:
            if not article.has_valid_references():
                continue
            count += 1
            try:
               (precision, accuracy) = Article.extract_references(article)
               precision_values.append(precision)
               accuracy_values.append(accuracy)
               print "[II] Current precision: %s, accuracy: %s after %s articles" % (numpy.array(precision_values).mean(), numpy.array(accuracy_values).mean(), count)
               print

            except Exception as e:
                print "[EE] Error occurred: %s" % e

        print
        print "=" * 80
        print "[II] Overall precision: %s, accuracy: %s" % (numpy.array(precision_values).mean(), numpy.array(accuracy_values).mean())

