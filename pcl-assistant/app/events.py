import hashlib
import hmac
import re
import unicodedata

ID=re.compile(r'^\d{1,40}$')

def valid_id(x):return isinstance(x,str) and bool(ID.fullmatch(x))

def verify_signature(body,signature,secret):
    if not secret or not isinstance(signature,str):return False
    expected='sha256='+hmac.new(secret.encode(),body,hashlib.sha256).hexdigest()
    return hmac.compare_digest(signature,expected)

def normalize_text(text):
    text=unicodedata.normalize('NFKC',text).lower().translate(str.maketrans({'ي':'ی','ى':'ی','ك':'ک','\u200c':' '}))
    text=''.join(c for c in text if unicodedata.category(c) not in ('Mn','Cf'))
    return ' '.join(re.findall(r'\w+',text))

def keyword_matches(text,keyword):
    return (' '+normalize_text(keyword)+' ') in (' '+normalize_text(text)+' ')

def normalize(payload,account,now):
    if not isinstance(payload,dict) or payload.get('object')!='instagram':return []
    entries=payload.get('entry',[])
    if not isinstance(entries,list):raise ValueError('entry must be array')
    result=[]
    for entry in entries:
        if not isinstance(entry,dict) or entry.get('id')!=account:continue
        for item in entry.get('messaging',[]):
            if not isinstance(item,dict):continue
            m=item.get('message') or {}; sender=item.get('sender',{}).get('id')
            if not isinstance(m,dict) or m.get('is_echo') or m.get('is_deleted') or sender==account:continue
            if not valid_id(sender) or item.get('recipient',{}).get('id')!=account or not isinstance(m.get('mid'),str):continue
            try:ts=float(item['timestamp'])/1000
            except (KeyError,ValueError,TypeError):continue
            if not 0<ts<=now+60:continue
            story=(m.get('reply_to') or {}).get('story') or {}
            text=m.get('text','')
            if not isinstance(text,str):continue
            kind='story' if story else 'dm'
            media=str(story.get('id','')) if isinstance(story,dict) else ''
            if m.get('is_unsupported') or m.get('attachments') or len(text)>4000:kind='unsupported'
            if not text and kind!='unsupported':continue
            mid=m['mid']
            if not mid or len(mid)>512:continue
            result.append(dict(id=f'{account}:message:{mid}',account=account,user_id=sender,username='',kind=kind,
                               text=text[:4000],media_id=media,timestamp=ts,created=now))
        for change in entry.get('changes',[]):
            if not isinstance(change,dict) or change.get('field')!='comments':continue
            v=change.get('value') or {}; frm=v.get('from') or {}; media=v.get('media') or {}
            cid=v.get('id') or v.get('comment_id'); uid=frm.get('id'); mid=media.get('id') or v.get('media_id')
            if not all(valid_id(i) for i in [cid,uid,mid]) or uid==account:continue
            if media.get('media_product_type')=='LIVE':continue
            # Never extend a private reply window using webhook receipt time.
            raw=v.get('timestamp') or v.get('created_time')
            ts=0
            if isinstance(raw,(int,float)):ts=float(raw)
            elif isinstance(raw,str):
                from datetime import datetime
                try:ts=datetime.fromisoformat(raw.replace('Z','+00:00')).timestamp()
                except ValueError:pass
            if ts>now+60:continue
            text=v.get('text','')
            if not isinstance(text,str):continue
            result.append(dict(id=f'{account}:comment:{cid}',account=account,user_id=uid,
                               username=str(frm.get('username',''))[:100],kind='comment',text=text[:4000],
                               media_id=mid,timestamp=ts,created=now))
    return result
