import json
import re
import threading
import time
import webbrowser
from datetime import datetime

from pytz import timezone, utc
from websocket_server import WebsocketServer

stripNonAN = re.compile(r'[^A-Za-z0-9 ]+')

class YoutubeLivechat:
    MAX_RETRIES = 3
 
    MESSAGES = None
    CALLBACKS = None
    THREAD_DONE = False

    CURRENT_CLIENT = None

    def __init__(self, youtubeVideoId, ytBcastService=None, wsPort=8778, callbacks=[]):
        self.MESSAGES = {}
        self.CALLBACKS = callbacks

        self.YT_BCAST_SERVICE = ytBcastService
 
        request = ytBcastService.liveBroadcasts().list(
            part="snippet,contentDetails,status",
            id=youtubeVideoId
        )
        response = request.execute()
        # print(response)

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
        self.CURRENT_CLIENT = client['id']

    def clientDisconnect(self, client, server):
        print("Client(%d) disconnected" % client['id'])

    def clientMessage(self, client, server, message):
        if client['id'] != self.CURRENT_CLIENT:
            print(f'Ignoring second client with id {client["id"]}...')
            return

        # this may have been solving a problem or causing one... we'll see
        # messageClean = message.encode('ascii', errors='ignore').decode()
        msgObject = json.loads(message)

        messageTime = self.try_parsing_date(msgObject['time']).replace(year=datetime.now().year,
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
                print("Adding Message From Chrome: %s" % msgObject)
                self.MESSAGES[msgObject['id']] = msgObject
                return
            case _:
                print("Unrecognized command from client: %s" % action)

    def try_parsing_date(self, text):
        for fmt in ('%I:%M %p', '%I:%M%p'):
            try:
                return datetime.strptime(text, fmt)
            except ValueError:
                pass
        raise ValueError('no valid date format found')

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
                # print("Messages in Response: %s" % len(chatGetResponse['items']))

                for message in chatGetResponse['items']:
                    print("Comparing Message From API: %s" % message)
                    if 'snippet' in message and 'textMessageDetails' in message['snippet']:
                        author = message['authorDetails']['displayName']
                        publishedTime = datetime.fromisoformat(message['snippet']['publishedAt'].split('.')[0]+'+00:00')
                        messageText = message['snippet']['textMessageDetails']['messageText']
                        messageText = messageText.encode('ascii', errors='ignore').decode().strip()

                        match, outstandingMessage = self.check_for_match(messageText, author, publishedTime, list(self.MESSAGES.items()))

                        if match:
                            del self.MESSAGES[match]
                            message['htmlText'] = outstandingMessage['content']
                            self.notify(message)
                    elif 'snippet' in message and 'superChatDetails' in message['snippet']:
                        author = message['authorDetails']['displayName']
                        publishedTime = datetime.fromisoformat(message['snippet']['publishedAt'].split('.')[0]+'+00:00')
                        messageText = message['snippet']['superChatDetails']['userComment']
                        messageText = messageText.encode('ascii', errors='ignore').decode().strip()

                        match, outstandingMessage = self.check_for_match(messageText, author, publishedTime, list(self.MESSAGES.items()))

                        if match:
                            del self.MESSAGES[match]
                            message['htmlText'] = outstandingMessage['content']
                            self.notify(message)                       
                    else:
                        print('Unknown Message Type:')
                        print(message)

                if len(self.MESSAGES) > 0:
                    retryCount -= 1
                else:
                    chatGetRequest = self.YT_BCAST_SERVICE.playlistItems().list_next(chatGetRequest, chatGetResponse)
            else:
                timeSincePoll = timeSincePoll + (0.25 * 1000)
                
                if retryCount <= 0:
                    print('Failed to get %s messages... clearing chrome queue...' % len(self.MESSAGES))
                    self.MESSAGES = {}
                    retryCount = self.MAX_RETRIES
        
            if self.THREAD_DONE:
                return

    def check_for_match(self, messageText, author, publishedTime, outstandingMessages):
        for id, outstandingMessage in outstandingMessages:
            outstandingMessageText = ''.join([str(item['text']) if item['type'] == 'text' else str(item['alt']) for item in outstandingMessage['content']])
            outstandingMessageText = ''.join([s for s in outstandingMessageText if s.isprintable()])
            outstandingMessageText = re.sub(' +', ' ', outstandingMessageText).strip()
            outstandingMessageTextRe = re.sub(r'[ \s\t]+', '[ ]*', stripNonAN.sub('', outstandingMessageText))

            print(f'\t"{messageText}" ?= "{outstandingMessageText}" OR "{outstandingMessageTextRe}" ?= "{stripNonAN.sub("", messageText)}"')
            print(f"\t{outstandingMessage['author']} == {author}")
            print(f"\t{abs((publishedTime - outstandingMessage['timestamp']).total_seconds())}")

            if ((outstandingMessageText == messageText or
                re.match(outstandingMessageTextRe, stripNonAN.sub('', messageText))) and
                outstandingMessage['author'] == author and 
                abs((publishedTime - outstandingMessage['timestamp']).total_seconds()) < 120):
                    return (id, outstandingMessage)
        return (None, None)


    def notify(self, message):
        for callback in self.CALLBACKS:
            callback(message)
