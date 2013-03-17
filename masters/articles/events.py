from django_socketio.events import on_connect, on_message, on_subscribe

@on_connect
def handle_connect(request, socket, context):
	print "Client connected!"
	socket.send({"message":"Hello"})
	pass


@on_subscribe(channel="articles")
def handle_subscribe(request, socket, context, channel):
	pass
