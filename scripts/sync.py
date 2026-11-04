# -*- coding: utf-8 -*-
"""
Miroir des barèmes d'indexation du Ministère de l'Équipement (Maroc).

Exécuté par le PC de l'utilisateur (toutes les 10 min, tâche Windows) : lit la page officielle des barèmes,
télécharge les PDF absents du dossier pdf/ (à partir de 2024) et met à jour
catalogue.json. L'application « Révision des Prix » lit ensuite ces fichiers via
raw.githubusercontent.com, que les navigateurs ont le droit de lire (CORS),
contrairement au site du Ministère.

Python 3 standard, sans dépendance.
"""
import json
import os
import sys
import time

ICI = os.path.dirname(os.path.abspath(__file__))
RACINE = os.path.dirname(ICI)
sys.path.insert(0, ICI)
from relais import construire_catalogue, fetch, PAGE_URL  # noqa: E402  (mêmes règles que le relais local)

DEPUIS = '2024-01'           # barèmes copiés dans le miroir (les plus anciens restent sur le site du Ministère)
PDF = os.path.join(RACINE, 'pdf')


def main():
    html, _ = fetch(PAGE_URL)
    cat = construire_catalogue(html.decode('utf-8', 'replace'))
    nouveaux, erreurs = [], []
    for e in cat['entrees']:
        if e['cle'] < DEPUIS:
            continue
        f = os.path.join(PDF, *e['local'].split('/'))
        if os.path.isfile(f):
            continue
        try:
            body, _ = fetch(e['url'], timeout=180)
            if not body.startswith(b'%PDF'):
                raise ValueError('le fichier reçu n\'est pas un PDF')
            os.makedirs(os.path.dirname(f), exist_ok=True)
            with open(f, 'wb') as fh:
                fh.write(body)
            nouveaux.append(e['local'])
            print('  +', e['local'], len(body) // 1024, 'Ko')
        except Exception as ex:                       # lien cassé sur le site, coupure réseau…
            erreurs.append('%s : %s' % (e['local'], ex))
            print('  ! ', e['local'], ex)
    entrees = []
    for e in cat['entrees']:
        f = os.path.join(PDF, *e['local'].split('/'))
        entrees.append({'cle': e['cle'], 'annee': e['annee'], 'mois': e['mois'], 'rectifie': e['rectifie'],
                        'url': e['url'], 'local': e['local'], 'miroir': os.path.isfile(f)})
    # Catalogue réécrit seulement s'il a changé (le PC vérifie toutes les 10 min : pas de commit inutile)
    chemin = os.path.join(RACINE, 'catalogue.json')
    try:
        with open(chemin, encoding='utf-8') as fh:
            ancien = json.load(fh).get('entrees')
    except Exception:
        ancien = None
    if ancien != entrees:
        data = {'genereLe': time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime()), 'source': PAGE_URL,
                'depuis': DEPUIS, 'entrees': entrees}
        with open(chemin, 'w', encoding='utf-8') as fh:
            json.dump(data, fh, ensure_ascii=False, indent=1)
    print('Nouveaux PDF :', len(nouveaux), '| erreurs :', len(erreurs))


if __name__ == '__main__':
    main()
