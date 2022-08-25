let ws = null;
let messagesTotal = 0;
let emojiCheck = /(?:[\u2700-\u27bf]|(?:\ud83c[\udde6-\uddff]){2}|[\ud800-\udbff][\udc00-\udfff]|[\u0023-\u0039]\ufe0f?\u20e3|\u3299|\u3297|\u303d|\u3030|\u24c2|\ud83c[\udd70-\udd71]|\ud83c[\udd7e-\udd7f]|\ud83c\udd8e|\ud83c[\udd91-\udd9a]|\ud83c[\udde6-\uddff]|\ud83c[\ude01-\ude02]|\ud83c\ude1a|\ud83c\ude2f|\ud83c[\ude32-\ude3a]|\ud83c[\ude50-\ude51]|\u203c|\u2049|[\u25aa-\u25ab]|\u25b6|\u25c0|[\u25fb-\u25fe]|\u00a9|\u00ae|\u2122|\u2139|\ud83c\udc04|[\u2600-\u26FF]|\u2b05|\u2b06|\u2b07|\u2b1b|\u2b1c|\u2b50|\u2b55|\u231a|\u231b|\u2328|\u23cf|[\u23e9-\u23f3]|[\u23f8-\u23fa]|\ud83c\udccf|\u2934|\u2935|[\u2190-\u21ff])/g

function addslashes( str ) {
    return (str + '').replace(/[\\"']/g, '\\$&').replace(/\u0000/g, '\\0');
}

function nodeInsertedCallback(event) {
    if(event.relatedNode.id == 'message' && event.path[4].childElementCount > messagesTotal) {      
        messagesTotal = event.path[4].childElementCount;
        console.log(event);
        
        var parent = event.relatedNode.closest('yt-live-chat-text-message-renderer');

        var messageId = parent.id;
        var authorName = parent.querySelectorAll('#author-name')[0].textContent;
        // var authorAvatarUrl = parent.querySelectorAll('yt-img-shadow #img')[0];
        var timestamp = parent.querySelectorAll('#timestamp')[0].innerHTML;

        msgParts = [];
        Array.from(event.relatedNode.childNodes).forEach(child => {
            msgParts.push(typeof child.data !== 'undefined' ? 
                          { 'type': 'text', 'text': child.data} : 
                          { 'type': 'img', 
                            'alt': child.alt ? (child.alt.match(emojiCheck) ? child.alt : ':'+child.alt+':') : '',
                            'text' : child.getAttribute('shared-tooltip-text') ? child.getAttribute('shared-tooltip-text') : '',
                            'src': child.src } );
        });

        notification = {
            'action': 'YT_MSG_EVENT',
            'id': messageId,
            'author': authorName,
            // 'authorAvatarUrl': authorAvatarUrl,
            'time': timestamp,
            'content': msgParts
        };

        console.log(notification);

        if (ws == null || ws.readyState != 1) {
        ws = new WebSocket("ws://localhost:8778/");
            // Delayed send on reconnect, wait for ready
            ws.onopen = function() {
                ws.send(JSON.stringify(notification));
            }
        } else {
            ws.send(JSON.stringify(notification));
        }
    }
};

document.addEventListener('DOMNodeInserted', nodeInsertedCallback);