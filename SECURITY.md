# Sécurité

## Signaler une vulnérabilité

Ne publiez pas de vulnérabilité ou de donnée sensible dans une issue publique.

Utilisez les avis de sécurité privés de GitHub lorsque cette fonctionnalité est disponible. À défaut, ouvrez une discussion privée avec le mainteneur avant toute publication.

## Données sensibles

Ce projet peut traiter des tickets Jira confidentiels. Ne commitez jamais :

- un fichier `.env` ou un mot de passe ;
- une base SQLite ou un export de tickets ;
- un rapport contenant des identifiants ou des descriptions internes ;
- une clé d'API, un jeton ou un certificat privé.

Les fichiers locaux produits par le pipeline sont exclus par `.gitignore`.

