let ws = null;
let messagesTotal = 0;
let emojiCheck = /(?:[\u2700-\u27bf]|(?:\ud83c[\udde6-\uddff]){2}|[\ud800-\udbff][\udc00-\udfff]|[\u0023-\u0039]\ufe0f?\u20e3|\u3299|\u3297|\u303d|\u3030|\u24c2|\ud83c[\udd70-\udd71]|\ud83c[\udd7e-\udd7f]|\ud83c\udd8e|\ud83c[\udd91-\udd9a]|\ud83c[\udde6-\uddff]|\ud83c[\ude01-\ude02]|\ud83c\ude1a|\ud83c\ude2f|\ud83c[\ude32-\ude3a]|\ud83c[\ude50-\ude51]|\u203c|\u2049|[\u25aa-\u25ab]|\u25b6|\u25c0|[\u25fb-\u25fe]|\u00a9|\u00ae|\u2122|\u2139|\ud83c\udc04|[\u2600-\u26FF]|\u2b05|\u2b06|\u2b07|\u2b1b|\u2b1c|\u2b50|\u2b55|\u231a|\u231b|\u2328|\u23cf|[\u23e9-\u23f3]|[\u23f8-\u23fa]|\ud83c\udccf|\u2934|\u2935|[\u2190-\u21ff])/g
let innerCleaner = /<[^>]*>/g

let videoId = null;

function addslashes( str ) {
    return (str + '').replace(/[\\"']/g, '\\$&').replace(/\u0000/g, '\\0');
}

setTimeout(function() {
    document.querySelectorAll("#label")[1].click();
    setTimeout(function() {
        document.querySelectorAll(".yt-simple-endpoint")[1].click();
        setTimeout(function() {
            // Select the node that will be observed for mutations
            const targetNode = document.querySelectorAll("div#items.yt-live-chat-item-list-renderer")[0]

            registerObserver(targetNode);
        }, 1000);
    }, 200);
}, 200);

// Options for the observer (which mutations to observe)
const config = { attributes: true, childList: true, subtree: true };

// Callback function to execute when mutations are observed
function sendUpdateToWSS(updateMsg) {
    if (ws == null || ws.readyState != 1) {
        ws = new WebSocket("ws://localhost:8778/?videoId="+videoId);

        // Delayed send on reconnect, wait for ready
        ws.onopen = function() {
            ws.send(updateMsg);
        }
    } else {
        ws.send(updateMsg);
    }

    messagesTotal += 1;
    console.log("Messages Total: "+messagesTotal);
    /* if(messagesTotal != 0 && messagesTotal % 20 == 0) {
        setTimeout(function() {
            document.querySelectorAll('#picker-buttons #button')[0].click();
            setTimeout(function() {
                document.querySelectorAll('#emoji')[3].childNodes[0].click()
                setTimeout(function() {
                    document.querySelectorAll('#picker-buttons #button')[0].click();
                }, 1000);
            }, 1000);
        }, 1000);
    } */
}

const callback = (mutationList, observer) => {
    for(const mutation of mutationList) {
        if(mutation.type == 'childList' && mutation.target.id == 'items' && mutation.addedNodes.length > 0) {
            for(const addedNode of mutation.addedNodes) {
                var messageId = addedNode.id;
                var authorName = addedNode.querySelectorAll('#author-name')[0].textContent;
                var timestamp = addedNode.querySelectorAll('#timestamp')[0].innerHTML;

                var msgParts = [];
                console.log(addedNode.querySelectorAll('#message'))
                for(const child of addedNode.querySelectorAll('#message')[0].childNodes) {
                    if(child instanceof HTMLAnchorElement || child instanceof HTMLSpanElement) {
                        msgParts.push({ 'type': 'text', 'text': child.innerHTML.replaceAll(innerCleaner, '')});
                    } else if (child instanceof Text) {
                        msgParts.push({ 'type': 'text', 'text': child.data});
                    } else if (child instanceof Image) {
                        msgParts.push({ 'type': 'img', 
                                        'alt': child.alt ? (child.alt.match(emojiCheck) ? child.alt : ':'+child.alt+':') : '',
                                        'text' : child.getAttribute('shared-tooltip-text') ? child.getAttribute('shared-tooltip-text') : '',
                                        'src': child.src });
                    } else if (child.tagName == "DIV" && child.childNodes[0] instanceof Image) {
                        msgParts.push({ 'type': 'img', 
                                        'alt': child.childNodes[0].alt,
                                        'text' : child.childNodes[0].alt,
                                        'src': child.childNodes[0].src });                        
                    }
                }

                notification = {
                    'action': 'YT_MSG_EVENT',
                    'id': messageId,
                    'videoId': videoId,
                    'author': authorName,
                    'time': timestamp,
                    'content': msgParts
                };

                console.log(notification);

                sendUpdateToWSS(JSON.stringify(notification));
            }
        }
    }
};

function registerObserver(targetNode) {
    const searchParams = new URLSearchParams(window.location.search);
    videoId = searchParams.get('v');

    // Create an observer instance linked to the callback function
    const observer = new MutationObserver(callback);

    // Start observing the target node for configured mutations
    observer.observe(targetNode, config);
}