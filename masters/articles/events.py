from django_socketio.events import on_connect, on_message, on_subscribe
from django.core.urlresolvers import reverse
from models import *
import time
from django.core.cache import cache

@on_connect
def handle_connect(request, socket, context):
	print "Client connected!"
	socket.send({"message":"Hello"})
	pass


@on_subscribe(channel="articles")
def handle_subscribe(request, socket, context, channel):
	pass


@on_message(channel="articles")
def handle_message(request, socket, context, message):
	action = message.get("action", None)
	print "Processing action: %s" % action
	if action == "next-article" or action == "get-article":
		if action == "next-article":
			last_id = cache.get("last_id", 0)
			training_set_id = message.get("training_set_id", None)
			print "The last id is %s" % last_id
			id = message.get("id", last_id)
			articles = Article.objects.filter(pk__gte=id, reviewed=False).order_by('pk')[:1]
		else:
			id = message.get("id")
			print "Loading requested id: %s" % id
			articles = [Article.objects.get(pk=id)]
		if articles:
			article = articles[0]
			if training_set_id and action == "next-article":
				(training_set, created) = TrainingSet.objects.get_or_create(pk=training_set_id)
				training_set.articles.add(article)
				training_set.save()
				print "Added %s to the training set %s" % (article, training_set_id)
			# send the article id
			ctx = {
				'action' : 'next-article',
				'id' : article.pk,
				'title' : article.title,
				'url' : reverse('review-article', kwargs={'id': article.pk}),
				'closeUrl' : reverse('close-article', kwargs={'id': article.pk}),
				'previewUrl' : reverse('preview-article', kwargs={'id' : article.pk}),
			}
			print "Sending article to client: %s" % article.title
			socket.send(ctx)
			cache.set("last_id", article.pk)
			print "Storing the last id as: %s" % article.pk

			# now find the references...
			article_references = article.article_references.all()
			references = [ {'id' : article_reference.pk, 
				'url' : reverse('review-reference', kwargs={'id':article_reference.pk }),
				'confirmUrl' : reverse('confirm-reference', kwargs={'id' :article_reference.pk }),
				'removeUrl' : reverse('remove-reference', kwargs={'id': article_reference.pk }),
				'contextReferenceUrl' : reverse('reference-context', kwargs={'id' : article_reference.pk }),
				} for article_reference in article_references ]
			
			ctx = {
				'action' : 'review-references',
				'references' : references,
			}
			socket.send(ctx)
	elif action == "close-article":
		id = message.get("id", None)
		if id:
			try:
				article = Article.objects.get(pk=id)
				article.close()
			except Article.DoesNotExist:
				pass
	
			
	




	