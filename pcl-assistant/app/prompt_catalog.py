"""Owner-curated public prompts: deterministic retrieval, no generated assets."""
import json
from .events import normalize_text,keyword_matches

class PromptCatalog:
    def __init__(self,public):self.p=public

    @staticmethod
    def save(db,data):
        title=data.get('title','');body=data.get('text','');aliases=data.get('aliases',[])
        if not isinstance(title,str) or not title.strip() or len(title)>100:raise ValueError('Invalid prompt title')
        if not isinstance(body,str) or not body.strip() or len(body.encode())>12000:raise ValueError('Invalid prompt text')
        if not isinstance(aliases,list) or len(aliases)>12 or any(not isinstance(a,str) or not normalize_text(a) or len(a)>100 for a in aliases):raise ValueError('Invalid aliases')
        active=data.get('active',True)
        if type(active) is not bool:raise ValueError('Invalid active flag')
        key=normalize_text(title)
        if not key:raise ValueError('Invalid title')
        db.execute('INSERT INTO public_prompts(id,title,text,aliases,active) VALUES(?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET title=excluded.title,text=excluded.text,aliases=excluded.aliases,active=excluded.active',
                   (key,title.strip(),body.strip(),json.dumps(aliases,ensure_ascii=False),int(active)))
        return key

    def answer(self,db,user,text,key):
        rows=list(db.execute('SELECT * FROM public_prompts WHERE active=1 ORDER BY title'))
        requested=keyword_matches(text,'پرامپت') or keyword_matches(text,'prompt') or text=='/prompts'
        matched=[]
        for row in rows:
            terms=[row['title'],*json.loads(row['aliases'])]
            if any(keyword_matches(text,term) for term in terms):matched.append(row)
        if not requested and not matched:return False
        if not matched:
            titles='\n'.join('• '+r['title'] for r in rows[:20])
            answer=('اسم یا موضوع پرامپت را بگو تا نسخهٔ ثبت‌شده را پیدا کنم.\n'+titles if rows else
                    'هنوز پرامپت تأییدشده‌ای در مخزن ثبت نشده. اسم پرامپتی که می‌خواهی را بگو؛ نسخه‌ای از طرف خودم به‌جای پرامپت PCL نمی‌سازم.')
            self.p.send(db,key,user,answer);return True
        exact=[r for r in matched if normalize_text(text)==normalize_text(r['title'])]
        if len(exact)==1:matched=exact
        if len(matched)>1:
            self.p.send(db,key,user,'چند پرامپت پیدا کردم؛ نام دقیق موردی را که می‌خواهی بفرست:\n'+'\n'.join('• '+r['title'] for r in matched[:20]));return True
        # Exact title resolves ambiguity when its alias also matches another asset.
        row=matched[0];answer=row['title']+'\n\n'+row['text']
        for part,start in enumerate(range(0,len(answer),3500)):
            self.p.send(db,key+':prompt:'+str(part),user,answer[start:start+3500])
        return True
