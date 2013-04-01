from django.core.management.base import BaseCommand, CommandError
from django.core.management import call_command
from datetime import timedelta, date, datetime
from django.conf import settings
from django.contrib.auth.models import Group, Permission
import os
import threading
from masters.articles.models import *

class Command(BaseCommand):
    args = ''
    help = 'Loads some test data'

    def handle(self, *args, **options):
    	""" 
    	This finds references for us
    	"""
        Gazetteer.find_references()
