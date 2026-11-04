# Barèmes d'indexation — Maroc (miroir)

Copie automatique des **barèmes d'indexation** publiés par le Ministère de l'Équipement et de l'Eau
sur [sa page officielle](https://www.equipement.gov.ma/Ingenierie/pages/revision-des-prix-baremes-indexation.aspx).

- `pdf/AAAA/MM_mois_AAAA.pdf` : les barèmes (depuis janvier 2024), à l'identique des fichiers du Ministère.
- `catalogue.json` : la liste des barèmes publiés (mois, lien officiel, présence dans le miroir).
- La mise à jour est faite par `scripts/sync.py` depuis un PC au Maroc (le site du Ministère refuse les connexions des serveurs GitHub), puis envoyée ici.

Ce miroir sert à l'application « Révision des Prix », dont le bouton **Actualiser les taux** lit les PDF ici :
le site du Ministère n'autorise pas une page web à lire ses fichiers, alors que GitHub le permet.

Les documents restent la propriété du Ministère ; **le barème officiel fait foi**.
