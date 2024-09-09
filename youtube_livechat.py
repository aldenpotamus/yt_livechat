import json
import re
import threading
import time
import webbrowser
from datetime import datetime
import re

from pytz import timezone, utc
from websocket_server import WebsocketServer

from urllib.parse import urlparse
from urllib.parse import parse_qs

stripNonAN = re.compile(r'[^A-Za-z0-9 ]+')

class YoutubeLivechat:
    MAX_RETRIES = 3
 
    MESSAGES = None
    CALLBACKS = None
    THREAD_DONE = False

    LIVE_CHAT_IDS = []
    CURRENT_CLIENTS = {}

    def __init__(self, youtubeVideoIds, ytBcastService=None, wsPort=8778, callbacks=[]):
        self.MESSAGES = {}
        self.CALLBACKS = callbacks

        self.YT_BCAST_SERVICE = ytBcastService
 
        for youtubeVideoId in youtubeVideoIds:
            self.CURRENT_CLIENTS[youtubeVideoId] = 'NULL'

            request = ytBcastService.liveBroadcasts().list(
                part="snippet,contentDetails,status",
                id=youtubeVideoId
            )
            response = request.execute()
            # print(response)

            self.LIVE_CHAT_IDS.append(response['items'][0]['snippet']['liveChatId'])

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
        print(f'New client connected and was given id {client["id"]}')

    def clientDisconnect(self, client, server):
        print("Client(%d) disconnected" % client['id'])

    def clientMessage(self, client, server, message):
        # this may have been solving a problem or causing one... we'll see
        # messageClean = message.encode('ascii', errors='ignore').decode()
        msgObject = json.loads(message)

        if msgObject["videoId"] not in self.CURRENT_CLIENTS.keys():
            print(f'Not currently monitoring videoId [{msgObject["videoId"]}]... ignoring message.')
            return
        elif self.CURRENT_CLIENTS[msgObject["videoId"]] == "NULL":
            print(f'New client identified as clientId[{client["id"]}] now linked to video [{msgObject["videoId"]}]')
            self.CURRENT_CLIENTS[msgObject['videoId']] = client["id"]

        if self.CURRENT_CLIENTS[msgObject['videoId']] == client["id"]: 
            print(f'Message from primary client {client["id"]} for video [{msgObject["videoId"]}]')  
        elif self.CURRENT_CLIENTS[msgObject['videoId']] < client["id"]:
            print(f'New primary client {client["id"]} for video [{msgObject["videoId"]}]')
            self.CURRENT_CLIENTS[msgObject['videoId']] = client["id"]
        else:
            print(f'Ignroing message from now defunct client [{client["id"]}] for video [{msgObject["videoId"]}]...')
            return

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
        thread = threading.Thread(target=self.start, args=[self.LIVE_CHAT_IDS])
        thread.start()
        return thread

    def done(self):
        self.THREAD_DONE = True

    def start(self, liveChatIds):
        liveChatExchanges = [{'liveChatId': liveChatId,
                              'request': self.YT_BCAST_SERVICE.liveChatMessages().list(liveChatId=liveChatId,part="snippet,authorDetails"),
                              'response': None}
                             for liveChatId in liveChatIds]

        chatGetResponse, delayTillPoll = self.get_messages_from_yt(liveChatExchanges)

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

                # chatGetResponse = chatGetRequest.execute()
                # delayTillPoll = chatGetResponse['pollingIntervalMillis']
                # print("Messages in Response: %s" % len(chatGetResponse['items']))

                chatGetResponse, delayTillPoll = self.get_messages_from_yt(liveChatExchanges)

                for message in chatGetResponse['items']:
                    # print("Comparing Message From API: %s" % message)
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
                timeSincePoll = timeSincePoll + (0.25 * 1000)
                
                if retryCount <= 0:
                    print(f'Failed to get {len(self.MESSAGES)} messages... clearing chrome queue...')
                    print(f'Message queue before clear: {self.MESSAGES}')
                    self.MESSAGES = {}
                    retryCount = self.MAX_RETRIES
        
            if self.THREAD_DONE:
                return

    def get_messages_from_yt(self, liveChatExchanges):       
        chatGetResponses = []
        for chatExchange in liveChatExchanges:
            # discard all existing chat messages
            if chatExchange['response']:
                chatExchange['request'] = self.YT_BCAST_SERVICE.liveChatMessages().list(liveChatId=chatExchange['liveChatId'],
                                                                                        pageToken=chatExchange['response']['nextPageToken'],
                                                                                        part="snippet,authorDetails")
            chatExchange['response'] = chatExchange['request'].execute()
            delayTillPoll = chatExchange['response']['pollingIntervalMillis']
            time.sleep(delayTillPoll / 1000)
            chatGetResponses.append(chatExchange['response'])

        result = {'items': []}

        for chatGetResponse in chatGetResponses:
            for item in chatGetResponse['items']:
                result['items'].append(item)

        return result, delayTillPoll / 1000

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
