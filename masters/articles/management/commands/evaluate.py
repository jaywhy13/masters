import os
import threading

from django.core.management.base import BaseCommand, CommandError
from django.core.management import call_command
from datetime import timedelta, date, datetime
from django.conf import settings
from django.contrib.auth.models import Group, Permission

import nltk
from nltk.classify import NaiveBayesClassifier

from masters.articles.models import *

class Command(BaseCommand):
    args = ''
    help = 'Evaluates our code using a NaiveBayes classifier'

    def handle(self, *args, **options):
    	""" Evaluates the system using a Naive Bayes classifier
    	"""
        print("Loading up references ...")
        invalid_references = [ get_reference(ref.pk) for ref in \
            ArticleReference.objects.filter(valid=False, confirmed=True)]
        valid_references = [ get_reference(ref.pk) for ref in \
            ArticleReference.objects.filter(valid=True, confirmed=True)]

        print("Extracting features ...")
        invalid_feats = [ (invalid_reference.extract_features(), "invalid") for \
            invalid_reference in invalid_references]
        valid_feats = [ (valid_reference.extract_features(), "valid") for \
            valid_reference in valid_references]

        invalid_cutoff = len(invalid_feats) * 3/4
        valid_cutoff = len(valid_feats) * 3/4

        training_feats = invalid_feats[:invalid_cutoff] + valid_feats[:valid_cutoff]
        test_feats = invalid_feats[invalid_cutoff:] + valid_feats[:valid_cutoff]

        print("Training the classifier")
        classifier = NaiveBayesClassifier.train(training_feats)

        # Now to test it
        accuracy = nltk.classify.accuracy(classifier, test_feats)            

        print("Accuracy now stands at: %s" % accuracy)



