# -*- coding: utf-8 -*-
"""
Relais local — Barèmes d'indexation (Ministère de l'Équipement)
================================================================
Le site equipement.gov.ma n'autorise pas un navigateur à lire ses pages/PDF
depuis une autre page (blocage CORS). Ce petit serveur, lancé sur VOTRE PC,
sert d'intermédiaire : index.html lui demande la page et les PDF, il les
télécharge et les renvoie au navigateur.

- Écoute uniquement sur 127.0.0.1 (inaccessible depuis le réseau).
- Ne relaie QUE des fichiers du site www.equipement.gov.ma.
- Aucune dépendance : Python 3 standard suffit.

Lancement : double-cliquer « Lancer_Serveur_Index.bat » (ou : python serveur_index.py)
"""
import json
import os
import re
import sys
import threading
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = 8765
HOST_SITE = "www.equipement.gov.ma"
BASE = "https://" + HOST_SITE
PAGE_URL = BASE + "/Ingenierie/pages/revision-des-prix-baremes-indexation.aspx"
VERSION = "1.1"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) RevisionPrix-RelaisLocal/" + VERSION

ICI = os.path.dirname(os.path.abspath(__file__))
DOSSIER = os.path.join(ICI, "Baremes_PDF")          # base de données des PDF
CATALOGUE_JS = os.path.join(DOSSIER, "catalogue.js")
MOIS = ["janvier", "fevrier", "mars", "avril", "mai", "juin", "juillet",
        "aout", "septembre", "octobre", "novembre", "decembre"]


def fetch(url, timeout=60):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read(), r.headers.get("Content-Type", "application/octet-stream")


# ------------------------------------------------------------------
# Catalogue : lecture des tableaux « BAREMES D'INDEXATION » du site.
# Ligne 1 de chaque tableau = années ; lignes suivantes = mois (janvier → décembre).
# ------------------------------------------------------------------
class _TableParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tables, self.autres = [], []
        self._t = self._tr = self._td = self._a = None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "table":
            self._t = []
        elif tag == "tr" and self._t is not None:
            self._tr = []
        elif tag == "td" and self._tr is not None:
            self._td = {"text": "", "links": []}
        elif tag == "a" and (a.get("href") or "").lower().endswith(".pdf"):
            self._a = {"href": a["href"], "text": ""}

    def handle_endtag(self, tag):
        if tag == "a" and self._a is not None:
            self._a["text"] = " ".join(self._a["text"].split())
            (self._td["links"] if self._td is not None else self.autres).append(self._a)
            self._a = None
        elif tag == "td" and self._td is not None:
            self._tr.append(self._td); self._td = None
        elif tag == "tr" and self._tr is not None:
            self._t.append(self._tr); self._tr = None
        elif tag == "table" and self._t is not None:
            self.tables.append(self._t); self._t = None

    def handle_data(self, d):
        if self._a is not None:
            self._a["text"] += d
        if self._td is not None:
            self._td["text"] += d


def _sans_accents(s):
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn").lower()


def construire_catalogue(html):
    p = _TableParser()
    p.feed(html)
    entrees, vus = [], set()
    for t in p.tables:
        if not t:
            continue
        annees = [re.sub(r"\D", "", c["text"]) for c in t[0]]
        if not annees or not all(len(a) == 4 for a in annees if a) or not any(annees):
            continue
        for i, ligne in enumerate(t[1:13]):
            for j, cell in enumerate(ligne):
                if j >= len(annees) or not annees[j]:
                    continue
                an, mm = int(annees[j]), i + 1
                for ln in cell["links"]:
                    href = ln["href"].replace(BASE, "")
                    rect = "rectifi" in href.lower()
                    if rect:
                        nom = urllib.parse.unquote(href.rsplit("/", 1)[-1])
                    else:
                        nom = "%02d_%s_%d.pdf" % (mm, MOIS[mm - 1], an)
                    local = "%d/%s" % (an, nom)
                    cle = (href, local)
                    if cle in vus:
                        continue
                    vus.add(cle)
                    entrees.append({"annee": an, "mois": mm, "cle": "%d-%02d" % (an, mm),
                                    "libelle": ln["text"] or MOIS[mm - 1], "rectifie": rect,
                                    "href": href, "url": BASE + href, "local": local})
    hrefs = {e["href"] for e in entrees}
    autres, vus2 = [], set()
    for ln in p.autres:
        href = ln["href"].replace(BASE, "")
        if href in hrefs or href in vus2:
            continue
        vus2.add(href)
        nom = urllib.parse.unquote(href.rsplit("/", 1)[-1])
        autres.append({"libelle": ln["text"] or nom, "href": href, "url": BASE + href, "local": "Autres/" + nom})
    entrees.sort(key=lambda e: (e["cle"], e["rectifie"]))
    return {"entrees": entrees, "autres": autres}


def chemin_local(rel):
    return os.path.join(DOSSIER, *rel.split("/"))


def ecrire_catalogue(cat):
    """Écrit Baremes_PDF/catalogue.js (lisible par index.html même hors-ligne)."""
    os.makedirs(DOSSIER, exist_ok=True)
    for e in cat["entrees"] + cat["autres"]:
        f = chemin_local(e["local"])
        e["present"] = os.path.isfile(f)
        e["taille"] = os.path.getsize(f) if e["present"] else 0
    data = {"genereLe": time.strftime("%Y-%m-%d %H:%M"), "source": PAGE_URL,
            "entrees": cat["entrees"], "autres": cat["autres"]}
    tmp = CATALOGUE_JS + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write("window.BAREMES_CATALOGUE = " + json.dumps(data, ensure_ascii=False, indent=1) + ";\n")
    os.replace(tmp, CATALOGUE_JS)
    return data


_CAT = {"par_href": {}}            # href → chemin local (pour enregistrer les PDF lus par « Actualiser »)
SYNC = {"en_cours": False, "fait": 0, "total": 0, "nouveaux": 0, "erreurs": [], "courant": "", "fin": None}
_lock = threading.Lock()


def charger_catalogue():
    html, _ = fetch(PAGE_URL)
    html = html.decode("utf-8", "replace")
    cat = construire_catalogue(html)
    _CAT["par_href"] = {e["href"]: e["local"] for e in cat["entrees"] + cat["autres"]}
    return html, cat


def enregistrer_pdf(href, body):
    rel = _CAT["par_href"].get(href)
    if not rel:
        return
    f = chemin_local(rel)
    if not os.path.isfile(f):
        os.makedirs(os.path.dirname(f), exist_ok=True)
        with open(f + ".tmp", "wb") as fh:
            fh.write(body)
        os.replace(f + ".tmp", f)


def synchroniser(log=None):
    """Télécharge tous les PDF absents du dossier Baremes_PDF puis réécrit catalogue.js."""
    with _lock:
        if SYNC["en_cours"]:
            return
        SYNC.update(en_cours=True, fait=0, total=0, nouveaux=0, erreurs=[], courant="lecture du site", fin=None)
    try:
        _, cat = charger_catalogue()
        ecrire_catalogue(cat)
        a_faire, vus = [], set()
        for e in cat["entrees"] + cat["autres"]:
            if e["local"] not in vus and not os.path.isfile(chemin_local(e["local"])):
                vus.add(e["local"]); a_faire.append(e)
        SYNC["total"] = len(a_faire)
        for i, e in enumerate(a_faire):
            SYNC["courant"] = e["local"]
            try:
                body, _ = fetch(e["url"], timeout=180)
                if not body.startswith(b"%PDF"):
                    raise ValueError("pas un PDF")
                f = chemin_local(e["local"])
                os.makedirs(os.path.dirname(f), exist_ok=True)
                with open(f + ".tmp", "wb") as fh:
                    fh.write(body)
                os.replace(f + ".tmp", f)
                SYNC["nouveaux"] += 1
                if log:
                    log("  [%d/%d] %s (%d Ko)" % (i + 1, len(a_faire), e["local"], len(body) // 1024))
            except Exception as ex:
                SYNC["erreurs"].append("%s : %s" % (e["local"], ex))
                if log:
                    log("  [%d/%d] ERREUR %s : %s" % (i + 1, len(a_faire), e["local"], ex))
            SYNC["fait"] = i + 1
            if (i + 1) % 10 == 0:
                ecrire_catalogue(cat)
        ecrire_catalogue(cat)
    except Exception as ex:
        SYNC["erreurs"].append("Site : %s" % ex)
    finally:
        SYNC.update(en_cours=False, courant="", fin=time.strftime("%Y-%m-%d %H:%M:%S"))


class Handler(BaseHTTPRequestHandler):
    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "*")
        self.send_header("Access-Control-Allow-Private-Network", "true")
        self.send_header("Cache-Control", "no-store")

    def _send(self, code, body, ctype):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self._cors()
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _json(self, code, obj):
        self._send(code, json.dumps(obj, ensure_ascii=False), "application/json; charset=utf-8")

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_GET(self):
        u = urllib.parse.urlsplit(self.path)
        q = urllib.parse.parse_qs(u.query)
        try:
            if u.path == "/ping":
                return self._json(200, {"ok": True, "version": VERSION, "site": PAGE_URL})

            if u.path == "/page":
                html, _ = charger_catalogue()
                return self._send(200, html, "text/html; charset=utf-8")

            if u.path == "/sync":          # lance le téléchargement des PDF manquants
                if not SYNC["en_cours"]:
                    threading.Thread(target=synchroniser, daemon=True).start()
                    time.sleep(0.2)
                return self._json(200, dict(SYNC, ok=True))

            if u.path == "/sync/status":
                return self._json(200, dict(SYNC, ok=True))

            if u.path == "/local":         # sert un PDF du dossier Baremes_PDF (lecture OCR)
                rel = (q.get("f") or [""])[0]
                f = os.path.normpath(chemin_local(rel))
                if (not rel.lower().endswith(".pdf") or ".." in rel
                        or not f.startswith(os.path.normpath(DOSSIER) + os.sep) or not os.path.isfile(f)):
                    return self._json(404, {"ok": False, "error": "PDF local introuvable : " + rel})
                with open(f, "rb") as fh:
                    return self._send(200, fh.read(), "application/pdf")

            if u.path == "/pdf":
                path = (q.get("path") or [""])[0]
                target = urllib.parse.urlsplit(BASE + path)
                # Sécurité : uniquement des .pdf du site du Ministère
                if (not path.startswith("/") or path.startswith("//") or ".." in path
                        or target.netloc != HOST_SITE
                        or not target.path.lower().endswith(".pdf")):
                    return self._json(400, {"ok": False, "error": "Chemin PDF refusé : " + path})
                body, _ = fetch(BASE + path, timeout=120)
                if not body.startswith(b"%PDF"):
                    return self._json(502, {"ok": False, "error": "Le fichier reçu n'est pas un PDF"})
                try:
                    enregistrer_pdf(path, body)   # alimente aussi la base de données PDF locale
                except Exception:
                    pass
                return self._send(200, body, "application/pdf")

            return self._json(404, {"ok": False, "error": "Route inconnue"})
        except urllib.error.HTTPError as e:
            return self._json(502, {"ok": False, "error": "Site du Ministère : HTTP %s" % e.code})
        except Exception as e:  # réseau coupé, timeout…
            return self._json(502, {"ok": False, "error": "Erreur réseau : %s" % e})

    def do_POST(self):
        u = urllib.parse.urlsplit(self.path)
        try:
            if u.path == "/globale":       # enregistre Baremes_PDF/base_globale.js
                n = int(self.headers.get("Content-Length") or 0)
                if n <= 0 or n > 50 * 1024 * 1024:
                    return self._json(400, {"ok": False, "error": "Taille invalide"})
                data = json.loads(self.rfile.read(n).decode("utf-8"))
                if not isinstance(data, dict) or not isinstance(data.get("baremes"), list):
                    return self._json(400, {"ok": False, "error": "Format invalide"})
                os.makedirs(DOSSIER, exist_ok=True)
                f = os.path.join(DOSSIER, "base_globale.js")
                with open(f + ".tmp", "w", encoding="utf-8") as fh:
                    fh.write("window.BASE_GLOBALE = " + json.dumps(data, ensure_ascii=False, separators=(",", ":")) + ";\n")
                os.replace(f + ".tmp", f)
                return self._json(200, {"ok": True, "baremes": len(data["baremes"])})
            return self._json(404, {"ok": False, "error": "Route inconnue"})
        except Exception as e:
            return self._json(500, {"ok": False, "error": str(e)})

    def log_message(self, fmt, *args):
        sys.stdout.write("  [%s] %s\n" % (self.log_date_time_string(), fmt % args))


def main():
    if "--sync" in sys.argv:   # mode ligne de commande : python serveur_index.py --sync
        print("Telechargement des baremes PDF dans", DOSSIER)
        synchroniser(log=lambda m: print(m, flush=True))
        print("Termine : %d nouveau(x), %d erreur(s)" % (SYNC["nouveaux"], len(SYNC["erreurs"])))
        for e in SYNC["erreurs"]:
            print("  ERREUR", e)
        return
    try:
        srv = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    except OSError:
        print("Le relais tourne deja (port %d occupe). Vous pouvez fermer cette fenetre." % PORT)
        return
    print("=" * 64)
    print(" Relais Index BAT6 actif sur http://127.0.0.1:%d" % PORT)
    print(" Laissez cette fenetre ouverte, puis cliquez sur")
    print(" « Actualiser les taux » dans l'application.")
    print(" (Ctrl+C ou fermer la fenetre pour arreter)")
    print("=" * 64)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
