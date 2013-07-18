import os
import sys
from optparse import make_option

from django.core.management.base import BaseCommand, CommandError
from django.core.management import call_command
from django.conf import settings

from openpyxl import Workbook
from nltk import FreqDist

from masters.articles.models import *

class Command(BaseCommand):
    args = ''
    help = 'Returns stats'

    option_list = BaseCommand.option_list + (
        make_option('--limit',
            action='store',
            dest='limit',
            default=100,
            metavar="LIMIT",
            help='Extracts blah'),
        make_option('--training-set',
            action='store',
            dest='training_set',
            default=None,
            help='Limits articles to a training set'),

        )


    def handle(self, *args, **options):
    	""" 
    	Finds references
    	"""
    	# Select limit articles
        limit = options["limit"]
        ctx = {
            "reviewed":True
        }
        if(options["training_set"]):
            training_set = TrainingSet.objects.get(pk=options["training_set"])
            print "[II] Limiting excel stats to training set %s" % training_set.pk
            ctx.update(dict(training_set=training_set))

        articles = Article.objects.filter(**ctx)[:limit]

        total = articles.count()

        wb = Workbook()
        ws = wb.get_active_sheet()
        rows = 0

        print "[II] Building Excel stats... please wait..."
        headers = ["PK"] + TESTS + ["Reference", "Description", "Valid?"]
        add_row(ws, 0, headers)
        rows += 1

        count = 1
        for article in articles:
            try:
                references = References(article.article_references.all())

                for reference in references.references:
                    times = int((count/float(total)) * 10)
                    bar = "[%s%s]" % (times * "#", (10-times) * " ")
                    sys.stdout.write("\r[II] Processing: %s of %s %s %s%s" % (count, total, bar, reference, " " * 40))
                    results = [reference.pk]
                    for test in TESTS:
                        result = reference.evaluate(test)
                        results.append("pass" if result else "fail")
                    results.append(reference.__unicode__())
                    results.append(reference.sentence)
                    results.append("valid" if reference.valid else "not valid")
                    add_row(ws, rows, results)
                    rows += 1
                count += 1
            except Exception as e:
                print e
                print "[II] Skipping article: %s - %s"  % (article.pk, article)
        wb.save("results.xlsx")
        print 


def percentage(amount, total, decimal_places=2):
    if total == 0:
        return "0.0%"
    return "%s" % round((amount / float(total)) * 100, decimal_places) + "%"
          
def avg(amount, total, decimal_places=2):
    if total == 0:
        return 0.0
    return round((amount / float(total)) * 1, decimal_places)


def add_row(ws, row, columns):
    for column in range(len(columns)):
        cell = ws.cell(row=row, column=column)
        cell.value = columns[column]