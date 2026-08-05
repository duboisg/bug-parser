# Bug Parser

Preuve de concept exploratoire visant à transformer des rapports de bugs de jeu vidéo en intelligence de production grâce à un pipeline LLM local et peu coûteux.

## Pourquoi ce projet existe

Dans le développement de jeux vidéo, une base de bugs contient davantage qu'une liste de corrections. Lorsqu'on analyse suffisamment de rapports, elle peut révéler des fragilités récurrentes dans la production d'assets, l'intégration, la configuration, le contenu, les tests ou les passages de relais entre équipes. Ces régularités sont intéressantes parce qu'elles permettent de remonter vers les systèmes et les processus qui produisent les bugs, au lieu de traiter uniquement leurs symptômes.

Bug Parser teste cette idée sur un flux volontairement spécifique : récupérer des tickets Bug QC depuis Jira, demander à un modèle d'inférence local d'identifier leur cause racine probable, puis agréger les résultats en vues utiles aux décisions de production. Le principe est généralisable à d'autres domaines : utiliser un LLM comme couche de classification de données opérationnelles non structurées, puis relier les catégories obtenues à des actions de prévention.

Le projet se situe au croisement de quatre domaines :

- le développement de jeux vidéo et ses chaînes de production ;
- le test et l'intelligence qualité ;
- l'inférence LLM locale pour structurer la donnée ;
- les décisions de production guidées par des régularités observables.

Il a été volontairement construit comme une preuve de concept réalisée rapidement. La question intéressante n'est pas de compter des bugs dans un tableau de bord, mais de vérifier si un modèle local modeste peut rendre une historique de bugs suffisamment lisible pour éclairer des décisions en amont.

## Ce que fait le prototype

```text
Tickets Bug QC Jira
        |
        v
Cache SQLite local  --->  Classification de cause racine par LLM local
        |                                  |
        +--------------------------------> |
                                           v
                              catégories, sous-systèmes, tags,
                              tendances de sévérité, équipes,
                              évolutions temporelles, doublons
                                           |
                                           v
                              rapport de production + tableau de bord
```

Le pipeline actuel propose :

- l'ingestion Jira avec filtres par projet, date, volume et requête JQL ;
- le stockage local SQLite des bugs et des analyses ;
- l'extraction JSON avec gestion tolérante des réponses du modèle ;
- des catégories de cause racine, sous-systèmes, tags, niveaux de confiance et états d'erreur ;
- des rapports dans le terminal et un tableau de bord Streamlit ;
- des répartitions par catégorie et sévérité, des matrices équipes/catégories, des tendances, des alertes sur les bugs à fort impact et un regroupement simple des doublons ;
- un point d'accès compatible OpenAI local, prévu pour un petit modèle exécuté sur la machine plutôt qu'une API d'inférence hébergée.

## Ce qui est démontré — et ce qui ne l'est pas

Le dépôt démontre une chaîne expérimentale complète : des données Jira existantes peuvent être récupérées, classifiées localement, stockées et transformées en vues permettant de discuter de régularités. Les erreurs du modèle sont également rendues visibles sous les états `llm_error` et `parse_error`, au lieu d'être silencieusement présentées comme des résultats.

Le projet ne démontre pas encore la précision de classification en production, une preuve de causalité, une comparaison systématique de modèles, une gouvernance de taxonomie ou un lien automatisé entre une régularité et une amélioration confirmée du processus. La revue humaine reste indispensable : les classifications sont des hypothèses à valider par les équipes qualité et production.

La prochaine évaluation crédible consisterait à constituer un échantillon relu manuellement et à mesurer l'accord sur les catégories, le calibrage de la confiance, le taux d'erreur et l'évolution des typologies de bugs récurrentes après action corrective.

## Local, privé et peu coûteux par conception

Le client d'inférence vise un serveur compatible OpenAI exécuté sur `127.0.0.1`, avec un modèle local configurable dans le code. Cette approche conserve les données Jira et les échanges d'inférence sur la machine, évite un coût par requête auprès d'un fournisseur distant et permet de remplacer le modèle sans réécrire le pipeline.

L'inférence locale est une contrainte expérimentale, pas une garantie que tous les modèles auront la même qualité. Les résultats dépendent de la taille du modèle, du prompt, de la fiabilité de la sortie structurée et de la qualité des tickets sources. Le prototype conserve donc les réponses brutes et les niveaux de confiance pour permettre une inspection réelle des résultats.

## Démarrage rapide

### 1. Installer les dépendances

```bash
python -m venv .venv
source .venv/bin/activate        # Windows : .venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configurer les services

Copier `.env.example` vers `.env` et fournir les identifiants d'une instance Jira à laquelle vous êtes autorisé à accéder. Démarrer un serveur d'inférence local compatible OpenAI sur `http://127.0.0.1:8080/v1`, ou adapter `src/llm_client.py` au serveur utilisé.

Le dépôt n'inclut volontairement ni export Jira, ni base SQLite, ni identifiant, ni rapport généré. Ces fichiers sont ignorés par Git, car les descriptions et métadonnées de tickets peuvent être confidentielles.

### 3. Exécuter le pipeline

```bash
python main.py sample --from-date 2026-01-01
```

Ou exécuter chaque étape séparément :

```bash
python main.py fetch --limit 50
python main.py analyze --retry-errors
python main.py report --no-narrative
streamlit run app.py
```

Les données produites sont écrites localement dans `output/` et ne doivent pas être publiées.

## Organisation du dépôt

- `main.py` — orchestration des commandes de récupération, analyse et rapport ;
- `src/jira_client.py` — récupération via l'API REST Jira ;
- `src/analyzer.py` — prompt et extraction structurée de la cause racine ;
- `src/llm_client.py` — client d'inférence local compatible OpenAI ;
- `src/store.py` — schéma et persistance SQLite ;
- `src/cluster.py` — agrégations et regroupement léger des doublons ;
- `src/report.py` — rapports dans le terminal et au format JSON ;
- `app.py` — tableau de bord Streamlit.

## État du projet

Preuve de concept exploratoire. Le code sert de base de discussion et d'évaluation ; il n'est pas présenté comme un système qualité prêt pour la production.

## Utilisation responsable

Ne connecter le pipeline qu'à des données Jira que vous êtes autorisé à traiter. Vérifier et anonymiser les exports avant de les partager. Conserver les identifiants dans des variables d'environnement, garder les bases générées hors du contrôle de version et considérer les sorties du modèle comme une aide à la décision soumise à validation humaine.

