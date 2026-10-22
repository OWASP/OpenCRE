"""Deterministic post-filters (same rules applied by hand in round 1), applied to fact id ranges."""
import re, sqlite3
ROLE = re.compile(r"leader|\blead\b|author|reviewer|translat|contributor|chair|director|treasurer|secretary|officer|ceo|manager|president|co-?founder|maintainer|engineer|developer|\bcto\b|\bciso\b|elected", re.I)
CNT = re.compile(r"\d[\d,\.]*\+?\s+(?:[\w\-]+\s+){0,3}(members|individuals|people|pages|resources|projects|risks|handbooks|contributors|leaders|chapters|categories|tools|participants|respondents|seats|votes|surveys|submissions|organizations|companies|countries|languages|translations|examples|sponsors|editions|releases|items|controls|requirements|checks)\b|(over|more than|about|nearly|total of)\s+\d[\d,]*", re.I)


def pass1(db, lo, hi):
    db.execute("delete from fact where id>? and id<=? and (rel in ('has_title','held_at','reviewed','maps_to','part_of') or lower(subj)=lower(obj) or length(subj)<3 or lower(subj)='content' or (rel in ('contributes','leads') and subj_type!='person') or (rel='released' and obj_type='organization') or (rel='released' and lower(quote) not like '%releas%' and lower(quote) not like '%published%' and lower(quote) not like '%launch%'))", (lo, hi))


def pass2(db, lo, hi):
    dele = []
    for i, rel, s, o, q in db.execute("select id,rel,subj,obj,quote from fact where id>? and id<=?", (lo, hi)).fetchall():
        bad = False
        if rel == "released" and not re.search("releas", q, re.I): bad = True
        elif rel in ("contributes", "role_of", "leads") and (not ROLE.search(q) or len(s.split()) < 2): bad = True
        elif rel == "has_count" and (not re.search(r"\d", o) or o not in q or re.search(r"score|rating|risk|\bid\b|^m\d|year|article|fee|\$|gdpr|t\+", q + s, re.I) or len(s) < 5 or not CNT.search(q)): bad = True
        if bad: dele.append((i,))
    db.executemany("delete from fact where id=?", dele)
