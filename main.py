import time
import sys
from youtube_livechat import YoutubeLivechat
import configparser

sys.path.append("..")
from auth_manager.auth_manager import AuthManager

def notifyFunction(message):
    print('NOTIFY: %s' % message['htmlText'])

if __name__ == '__main__':
    videoIds = sys.argv[1].split(',')

    print(f'Running for streams: {videoIds}')

    del sys.argv[1]

    print('Parsing config file...')
    CONFIG = configparser.ConfigParser()
    CONFIG.read('config.ini')

    bcastService = AuthManager.get_authenticated_service(CONFIG['TEST'], 
                                                         authConfig=CONFIG['AUTH_MANAGER'])

    ytMonitor = YoutubeLivechat(videoIds,
                                ytBcastService=bcastService,
                                callbacks=[notifyFunction])
    
    #ytMonitor.start()
    
    ytMonitor.nonblockingStart()

    try:
        while True:
            time.sleep(3)
    except KeyboardInterrupt:
        ytMonitor.done()