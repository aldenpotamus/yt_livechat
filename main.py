import time
import sys
from youtube_livechat import YoutubeLivechat

sys.path.append("..")
from auth_manager.auth_manager import AuthManager

def notifyFunction(message):
    print('NOTIFY: %s' % message['htmlText'])

if __name__ == '__main__':
    videoId = sys.argv[1]
    print('Running for stream: %s' % videoId)

    del sys.argv[1]

    bcastService = AuthManager.get_authenticated_service("broadcast",
                                                         clientSecretFile='client_secret.json',
                                                         scopes=["https://www.googleapis.com/auth/youtube.force-ssl"])

    ytMonitor = YoutubeLivechat(videoId,
                                ytBcastService=bcastService,
                                callbacks=[notifyFunction])
    
    #ytMonitor.start()
    
    ytMonitor.nonblockingStart()

    try:
        while True:
            time.sleep(3)
    except KeyboardInterrupt:
        ytMonitor.done()