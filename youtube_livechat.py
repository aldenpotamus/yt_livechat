import json
import os
import sys
import time
import webbrowser
from datetime import datetime
from pytz import timezone
from pytz import utc
import threading

import google_auth_oauthlib.flow
import googleapiclient.discovery
import googleapiclient.errors
from websocket_server import WebsocketServer

class YoutubeLivechat:
    MAX_RETRIES = 3
 
    MESSAGES = None
    CALLBACKS = None
    THREAD_DONE = False

    def __init__(self, youtubeVideoId, ytBcastService=None, wsPort=8778, callbacks=[]):
        self.MESSAGES = {}
        self.CALLBACKS = callbacks

        self.YT_BCAST_SERVICE = ytBcastService
 
        request = ytBcastService.liveBroadcasts().list(
            part="snippet,contentDetails,status",
            id=youtubeVideoId
        )
        response = request.execute()
        print(response)

        global liveChatId
        liveChatId = response['items'][0]['snippet']['liveChatId']

        webbrowser.open_new_tab('https://www.youtube.com/live_chat?is_popout=1&v='+youtubeVideoId)

        global websocketServer
        websocketServer = WebsocketServer(port=wsPort, host='0.0.0.0')
        websocketServer.set_fn_new_client(self.clientJoin)
        websocketServer.set_fn_client_left(self.clientDisconnect)
        websocketServer.set_fn_message_received(self.clientMessage)
        websocketServer.run_forever(True)

    def registerNewCallback(self, callback):
        self.CALLBACKS.append(callback) 

    def clientJoin(self, client, server):
        print("New client connected and was given id %d" % client['id'])

    def clientDisconnect(self, client, server):
        print("Client(%d) disconnected" % client['id'])

    def clientMessage(self, client, server, message):
        msgObject = json.loads(message)
        messageTime = datetime.strptime(msgObject['time'], '%I:%M %p').replace(year=datetime.now().year,
                                                                               month=datetime.now().month,
                                                                               day=datetime.now().day)
        localtime = timezone('US/Pacific')
        localtime = localtime.localize(messageTime, is_dst=None)
        msgObject['timestamp'] = localtime.astimezone(utc)
                                                    
        # print("Timestamp from Chrome: "+str(msgObject['timestamp']))
        # print("Author from Chrome: "+str(msgObject['author']))
        # print("Message from Chrome: "+str(messageTextOnly(msgObject)))
        action = msgObject['action']

        match action:
            case 'YT_MSG_EVENT':
                print("ID: %s" % msgObject['id'])
                self.MESSAGES[msgObject['id']] = msgObject
                return
            case _:
                print("Unrecognized command from client: %s" % action)

    def nonblockingStart(self):
        self.THREAD_DONE = False
        thread = threading.Thread(target=self.start)
        thread.start()
        return thread

    def done(self):
        self.THREAD_DONE = True

    def start(self):
        chatGetRequest = self.YT_BCAST_SERVICE.liveChatMessages().list(
            liveChatId=liveChatId,
            part="snippet,authorDetails"
        )

        # discard all existing chat messages
        chatGetResponse = chatGetRequest.execute()
        delayTillPoll = chatGetResponse['pollingIntervalMillis']
        chatGetRequest = self.YT_BCAST_SERVICE.playlistItems().list_next(chatGetRequest, chatGetResponse)

        delayTillPoll = 0      
        timeSincePoll = 0
        retryCount = self.MAX_RETRIES

        while True:
            time.sleep(0.25)

            if len(self.MESSAGES) == 0:
                retryCount = self.MAX_RETRIES

            # print("Messages Outstanding: %s, Retrys: %s, Time Since Poll: %s, Delay Till Poll: %s" % (len(self.MESSAGES), retryCount, timeSincePoll, delayTillPoll))
            if (len(self.MESSAGES) > 0) and (retryCount > 0) and (timeSincePoll > delayTillPoll):
                time.sleep(2.00)
                timeSincePoll = 0

                chatGetResponse = chatGetRequest.execute()
                delayTillPoll = chatGetResponse['pollingIntervalMillis']

                likelyMatch = False
                for message in chatGetResponse['items']:
                    author = message['authorDetails']['displayName']
                    publishedTime = datetime.fromisoformat(message['snippet']['publishedAt'].split('.')[0]+'+00:00')
                    messageText = message['snippet']['textMessageDetails']['messageText']

                    for id, outstandingMessage in list(self.MESSAGES.items()):
                        match = True

                        if outstandingMessage['author'] == author and abs((publishedTime - outstandingMessage['timestamp']).total_seconds()) < 120:
                            for textItem in [item['text'] for item in outstandingMessage['content'] if item['type'] == 'text']:
                                if textItem not in messageText:
                                    match = False
                    
                        if match:
                            del self.MESSAGES[id]
                            message['htmlText'] = outstandingMessage['content']
                            self.notify(message)

                if len(self.MESSAGES) > 0:
                    retryCount -= 1
                    chatGetRequest = self.YT_BCAST_SERVICE.playlistItems().list_next(chatGetRequest, chatGetResponse)
            else:
                timeSincePoll = timeSincePoll + (0.25 * 1000)
                
                if retryCount <= 0:
                    print('Failed to get %s messages... clearing chrome queue...' % len(self.MESSAGES))
                    self.MESSAGES = {}
                    retryCount = self.MAX_RETRIES
        
            if self.THREAD_DONE:
                return


    def notify(self, message):
        for callback in self.CALLBACKS:
            callback(message)