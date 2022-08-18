setTimeout(function() {
    var s = document.createElement('script');
    s.src = chrome.runtime.getURL('registerObserver.js');
    s.onload = function() { this.remove(); };
    (document.head || document.documentElement).appendChild(s);
}, 1000);