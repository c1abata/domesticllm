#!/usr/bin/env python3
"""Dependency-free operator WebChat for the local llama.cpp API."""

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


PAGE = r"""<!doctype html>
<html lang="it"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>CPU Inference WebChat</title>
<style>
body{max-width:900px;margin:2rem auto;padding:0 1rem;background:#101317;color:#e7edf3;font:16px system-ui,sans-serif}
h1{margin-bottom:.25rem}.hint{color:#aab6c3}#chat{min-height:55vh;border:1px solid #33404c;border-radius:8px;padding:1rem;overflow:auto}
.message{white-space:pre-wrap;padding:.7rem;margin:.7rem 0;border-radius:7px}.user{background:#1d3b57}.assistant{background:#1b252e}.error{background:#5b2222}
form{display:flex;gap:.7rem;margin-top:1rem}textarea{flex:1;min-height:4rem;padding:.7rem;font:inherit}button{padding:.7rem 1rem;font:inherit}
</style>
<body><h1>CPU Inference WebChat</h1><p class="hint">Qwen3-Coder 30B · CPU · operatore locale</p>
<main id="chat" aria-live="polite"></main>
<form id="form"><textarea id="prompt" autofocus placeholder="Scrivi un messaggio…"></textarea><button id="send" type="submit">Invia</button></form>
<script>
const model='/srv/local-ai/models/Qwen3-Coder-30B-A3B-Instruct-UD-Q4_K_XL.gguf';
const base=`${location.protocol}//${location.hostname}:8080/v1`;
const history=[]; const chat=document.querySelector('#chat'); const form=document.querySelector('#form');
const prompt=document.querySelector('#prompt'); const send=document.querySelector('#send');
function add(role,text){const e=document.createElement('article');e.className=`message ${role}`;e.textContent=text;chat.append(e);chat.scrollTop=chat.scrollHeight;return e}
form.addEventListener('submit',async event=>{event.preventDefault();const text=prompt.value.trim();if(!text)return;prompt.value='';history.push({role:'user',content:text});add('user',text);send.disabled=true;prompt.disabled=true;const out=add('assistant','…');try{const response=await fetch(`${base}/chat/completions`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({model,messages:history,temperature:.7})});if(!response.ok)throw new Error(`HTTP ${response.status}: ${await response.text()}`);const data=await response.json();const answer=data.choices?.[0]?.message?.content;if(!answer)throw new Error('Risposta priva di contenuto');history.push({role:'assistant',content:answer});out.textContent=answer}catch(error){out.className='message error';out.textContent=`Richiesta fallita: ${error.message}`}finally{send.disabled=false;prompt.disabled=false;prompt.focus()}});
</script></body></html>"""


class WebChatHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path != "/":
            self.send_error(404)
            return
        body = PAGE.encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        print(f"webchat {self.client_address[0]} {fmt % args}", flush=True)


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", 8081), WebChatHandler).serve_forever()
