Duo — un dossier, deux regards

Ouvrir « Ouvrir Duo.command » par un double-clic. Aucune commande à saisir. Garder le Mac et le relais ouverts pendant l’utilisation.

Duo utilise les programmes officiels Codex et Claude Code connectés à vos abonnements. La connexion au site Claude ou à Claude Desktop ne suffit pas pour connecter Claude Code. Aucun basculement vers une clé API n’est prévu. Chaque réponse consomme les quotas des abonnements ; désactiver les crédits supplémentaires et achats automatiques dans les comptes.

Interface hébergée
Vercel héberge uniquement la page et le téléchargement du relais. Les pièces, projets, messages, réponses et identifiants des assistants ne sont pas envoyés au serveur Vercel. La page communique directement avec le relais sur ce Mac, au port 8786. La connexion se fait depuis le lanceur ; son jeton temporaire est transmis dans un fragment d’adresse et immédiatement retiré de l’adresse par la page. Aucun jeton n’est publié dans le dépôt.
Le navigateur peut demander l’autorisation d’accès au réseau local pour cette page. Les autres ordinateurs ne peuvent pas utiliser les abonnements de ce Mac via ce relais. Le relais accepte seulement les origines locales et l’adresse exacte déclarée dans hosting.json.

Aucune mémoire dans Duo
Chaque onglet dispose d’une discussion indépendante. Duo ne crée ni historique sur disque, ni base de données, ni stockage dans le navigateur. Les pièces et résultats restent en mémoire pour pouvoir continuer la discussion ou les télécharger tant que l’onglet reste ouvert.
« Terminer et effacer » interrompt les assistants et supprime pièces, messages et livrables de la discussion. Fermer ou actualiser l’onglet demande aussi cette suppression. En cas de crash, perte de connexion ou signal non reçu, le relais annule et efface une session après deux minutes sans contact (contrôle toutes les cinq secondes). Une réouverture ne récupère jamais la discussion précédente.
Téléchargez les résultats à conserver avant de terminer. Les fichiers téléchargés volontairement restent sur votre ordinateur. Les fournisseurs et leurs programmes peuvent conserver leurs propres journaux selon leurs réglages : l’effacement Duo n’est pas une suppression de ces journaux.
Les extractions et appels utilisent brièvement des dossiers temporaires supprimés à la sortie de leur traitement. Un import déjà en cours peut finir son nettoyage après la fermeture ; il ne peut pas réintroduire des données dans une session fermée.

Pièces et projets
Joindre PDF, Word DOCX, Excel XLSX, PowerPoint PPTX, texte, code, PNG, JPEG ou ZIP : dix pièces, 12 Mo par pièce, 30 Mo par discussion. Vérifier le texte extrait avant de lancer. Les images et scans sont reconnus en texte ; la mise en page et les graphiques ne sont pas vérifiés visuellement.
« Choisir le dossier du projet » importe une copie de lecture ; « Cloner et joindre » accepte un lien GitHub HTTPS et une branche facultative. On peut aussi demander de cloner un lien GitHub dans la demande initiale. Dépôts privés : connexion GitHub locale existante. Les deux assistants reçoivent la même copie des fichiers de code et un inventaire.
Dépendances, caches, fichiers générés, secrets détectés, binaires, liens symboliques et sous-modules sont exclus. Les règles .gitignore sont appliquées. Vérifier l’inventaire et les exclusions ; la détection automatique ne garantit pas de trouver tous les secrets. Maximum 5 000 fichiers de code, 1 Mo par fichier et 30 Mo de code. Les originaux restent inchangés et l’import n’exécute aucun code du projet.

Modes
Avis séparés : deux analyses du même dossier, sans accès à l’avis de l’autre.
Relecture croisée : analyse, critique avec les sources, puis réponse et révision.
Recherche d’accord : deux avis indépendants, puis confrontation ; arrêt anticipé seulement si les deux déclarent un accord sans point ouvert et citent toutes les pièces. Un accord déclaré ne constitue pas une preuve d’exactitude.
Discussion libre : échanges alternés puis synthèse.
Une fois les réponses produites, la discussion reste ouverte pour télécharger ou poser une question complémentaire. « Terminer et effacer » la clôt définitivement.

Livrables et transmission
Les assistants peuvent faire construire DOCX, PDF, XLSX, PPTX, CSV, TSV, TXT, Markdown, HTML, JSON, XML, YAML, SVG, PNG, JPG, ZIP et fichiers de code. Jusqu’à six fichiers par réponse et 60 Mo de livrables par discussion. Audio, vidéo, formats propriétaires spécialisés, macros et photographies génératives ne sont pas pris en charge.
Duo construit les vrais fichiers, relit leur contenu et transmet automatiquement le texte extrait, leur structure, leur empreinte et les limites de lecture à l’autre assistant. Ce n’est pas une vérification visuelle du rendu. Les classeurs sont recalculés avec LibreOffice ; liens et formules externes sont refusés. Le code généré est téléchargeable mais n’est pas exécuté par ce constructeur.
« Exporter cette analyse » crée Word, PDF ou texte sans nouvel appel au modèle. « Télécharger le dossier complet » rassemble originaux, extractions, analyses, livrables et trace des transmissions.

Installation locale actuelle
Python et les programmes Codex et Claude Code sont nécessaires. Les bibliothèques documentaires et LibreOffice proviennent du runtime Codex installé sur ce Mac. L’OCR utilise Vision de macOS (bin/duo-ocr ; source ocr.swift). Ce relais personnel est préparé pour le Mac de Perrine, pas un installateur universel.
Claude Code n’a aucun outil hors projets. Pour un projet, seuls les outils de lecture/recherche sont proposés. Les MCP, hooks et commandes personnalisées sont désactivés. Codex travaille en lecture seule dans un dossier temporaire, sans configuration utilisateur. La lecture seule n’est pas une isolation complète de tous les fichiers du Mac.

Publication
Le dépôt contient uniquement le code de Duo. build_web.py produit web/index.html et une archive du relais à partir d’une liste explicite de fichiers, sans identifiants ni discussions. Vercel sert ce dossier statique. Le projet GitHub relié permet les mises à jour depuis main.
