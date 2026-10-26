Duo 0.2 — application personnelle installable (version de test)

Installation sans terminal
Mac : ouvrir l’image DMG, glisser Duo dans Applications, puis ouvrir Duo.
Windows : ouvrir Duo-Windows-x64-Setup.exe et suivre l’assistant. Installation pour l’utilisateur courant, sans droits administrateur.
Une fenêtre Duo propose « Ouvrir Duo et mes connexions » et « Quitter Duo ». L’interface s’ouvre dans le navigateur, sur une adresse locale. Garder l’application ouverte pendant les échanges.

Première utilisation
Dans « Mes connexions », cliquer sur « Installer Codex officiel » et « Installer Claude Code officiel ». Les programmes sont téléchargés depuis les sources officielles, avec une version et une empreinte SHA-256 fixes. Leurs binaires ne sont pas modifiés.
Cliquer ensuite sur « Connecter mon abonnement ». La procédure officielle s’ouvre dans le navigateur. Choisir son propre compte et terminer la connexion. Si le fournisseur demande de recopier un code, le champ de l’interface Duo permet de le faire sans terminal.
Aucun compte de Perrine n’est livré ou récupéré. Les profils Codex et Claude Code de Duo sont distincts de ceux des autres applications installées. Les clés API présentes dans l’environnement ne sont pas utilisées. Les réponses nécessitent que les deux programmes reconnaissent une connexion d’abonnement.
Les connexions restent locales et enregistrées pour les prochaines ouvertures ; « Déconnecter » déconnecte seulement le profil Duo. Les comptes sont facturés directement par leurs fournisseurs et leurs quotas et conditions s’appliquent. Désactiver les crédits supplémentaires et achats automatiques dans les comptes pour rester sur les abonnements ; Duo ne lit ni ne modifie ces réglages et ne garantit pas un plafond de facturation chez les fournisseurs.

Données
Aucun historique, base de données ou stockage de discussion dans le navigateur. Chaque onglet a une discussion indépendante. Les pièces, instantanés de projets, messages et livrables restent en mémoire tant que la discussion reste ouverte. « Terminer et effacer », fermer ou actualiser l’onglet les efface et annule les assistants. Si le navigateur disparaît sans prévenir, expiration après deux minutes sans contact, vérifiée toutes les cinq secondes.
Télécharger les fichiers à conserver avant de terminer. Les téléchargements volontaires restent sur l’ordinateur. Les connexions personnelles sont conservées séparément des discussions. Les fournisseurs et leurs programmes peuvent conserver leurs propres journaux ; Duo ne supprime pas ces journaux.
Les extractions et créations utilisent brièvement des dossiers temporaires supprimés à la fin du traitement. Un import en cours peut finir son nettoyage après la fermeture sans réintroduire de données dans la session fermée.
Aucune lecture automatique du dossier personnel ni recherche de projets au démarrage. L’application distribuée ne contient ni compte, ni document, ni projet de l’éditeur. Les assistants travaillent sur les pièces fournies et une copie des projets sélectionnés. La lecture seule des outils n’est pas une isolation complète de tous les fichiers du compte utilisateur : n’ouvrir que des dossiers de confiance.

Fonctions
Avis séparés, relecture croisée, recherche d’accord et discussion libre. Les pièces et analyses passent automatiquement entre les assistants ; les réserves restent visibles. Un accord déclaré n’est pas une preuve d’exactitude.
Pièces PDF, DOCX, XLSX, PPTX, texte, images et ZIP : dix pièces, 12 Mo par pièce et 30 Mo au total. Images/scans : texte reconnu par macOS Vision ou Windows OCR, sans validation visuelle des graphiques, signatures et mises en page. Windows doit disposer d’une langue OCR compatible.
Projets : sélectionner un dossier ou indiquer un dépôt GitHub et une branche. Une copie filtrée et son inventaire sont fournis aux deux assistants, sans installation ni exécution du projet. Dépendances, caches, binaires et secrets détectés sont exclus. Contrôler l’inventaire ; la détection des secrets n’est pas exhaustive. Limites : 5 000 fichiers de code, 1 Mo par fichier et 30 Mo de code.
Le clonage GitHub nécessite Git, installable graphiquement depuis git-scm.com. L’import d’un dossier et ses règles .gitignore fonctionnent aussi sans Git. Les dépôts privés utilisent uniquement la connexion GitHub disponible sur l’ordinateur de l’utilisateur.
Livrables DOCX, PDF, XLSX, PPTX, CSV, texte, HTML, JSON, SVG, PNG/JPG (dessins), ZIP et code. Six fichiers par réponse et 60 Mo de livrables. Les vrais fichiers sont construits puis relus en texte/structure avant transmission. Audio, vidéo, macros, photos génératives et formats propriétaires spécialisés non pris en charge.
Les classeurs sans formules fonctionnent immédiatement. Le recalcul de formules nécessite LibreOffice, installable graphiquement. Sans LibreOffice, un classeur à formules est refusé avec une explication ; aucun résultat non recalculé n’est présenté comme validé. Le code généré n’est pas exécuté.

Distribution et limites de cette version de test
Paquets Mac Apple Silicon, Mac Intel et Windows x64. Les builds Mac sont préparés sur macOS 15 ; compatibilité avec des versions plus anciennes non validée. Windows ARM et Linux ne sont pas encore distribués.
Les paquets de test ne sont pas signés avec un certificat de développeur reconnu par Apple ou Microsoft ; les systèmes peuvent afficher un avertissement. La signature et la notarisation de distribution demandent les comptes/certificats de l’éditeur et ne sont pas incluses dans cette version. Ne pas désactiver les protections de l’ordinateur.
Les essais automatiques vérifient les profils vides, les fichiers, les sessions et le démarrage autonome. Une connexion réelle avec le compte personnel de chaque utilisateur reste nécessaire. Les conditions d’OpenAI et Anthropic, notamment celles d’intégration de Claude Code, restent applicables ; Duo n’est pas un produit officiel de ces fournisseurs.

Fabrication
build_desktop.py crée les applications avec une liste de ressources explicite et les bibliothèques installées. Aucun dossier personnel, cache d’authentification, fichier .env ou projet de travail n’est inclus. La procédure GitHub Actions « Fabriquer les installateurs Duo » construit et contrôle les trois systèmes sur leurs propres machines.
Vercel peut héberger l’interface et les liens de téléchargement ; les pièces et les connexions ne transitent pas par Vercel. L’application installée fonctionne avec sa propre interface locale et ne dépend pas du Mac de l’éditeur.
