// ==UserScript==
// @name         NUC QA script
// @namespace    http://tampermonkey.net/
// @version      2025-07-10
// @description  try to take over the world!
// @author       You
// @match        https://development.instructure.com/*
// @icon         https://www.google.com/s2/favicons?sz=64&domain=instructure.com
// @grant        none
// ==/UserScript==
(function() {
    'use strict';
    const script1 = document.createElement('script');
    script1.src = 'https://d1dwacz2r65vub.cloudfront.net/chatbot-layer.js';
    document.head.appendChild(script1);
})();