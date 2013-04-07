from django.http import HttpResponse
from django.shortcuts import render_to_response
from django.template import RequestContext

def home(request):
	article_id = request.GET.get("article_id", None)
	return render_to_response("index.html", context_instance=RequestContext(request, locals()))
