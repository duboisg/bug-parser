# Contribuer

Les contributions sont les bienvenues, en particulier sur :

- l'évaluation de la qualité des classifications ;
- la robustesse de l'extraction JSON ;
- la mesure du coût et du temps d'inférence local ;
- l'anonymisation et la protection des données Jira ;
- la généralisation du pipeline à d'autres données opérationnelles.

Avant de proposer une modification :

1. vérifier que les données Jira et les secrets restent hors du dépôt ;
2. décrire clairement le comportement attendu ;
3. lancer `python -m compileall -q app.py main.py src` ;
4. mettre à jour la documentation si le fonctionnement visible change.

Les sorties d'un modèle doivent être présentées comme des hypothèses vérifiables, jamais comme des causes certaines sans validation humaine.

