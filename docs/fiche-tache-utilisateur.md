# ECUME : fiche de tâche et guide des champs

Version du guide : 16 septembre 2026. Décrit le MVP local actuel, y compris le lot Echo OWL / VOC / SHACL non encore publié.

**But : transformer un document métier en connaissances compréhensibles, vérifiées et réutilisables.**

Le parcours principal reste : **comprendre → décider → approfondir si nécessaire**.
Les exemples de cette fiche sont uniquement pédagogiques. Ils ne sont pas des documents importés ni des règles à appliquer.

## 1. La tâche en une minute

| Étape | Ce que vous faites | Ce que fait ECUME | Résultat à vérifier |
| --- | --- | --- | --- |
| Préparer | Choisir et tester le modèle dans Admin. | Enregistre la configuration et vérifie la connexion. | Le test réussit ; le modèle choisi est le bon. |
| Préparer Echo, si nécessaire | Importer les trois fichiers du même référentiel. | Lit les copies locales et construit le profil OWL / VOC / SHACL. | Les trois couches appartiennent au même référentiel. |
| Importer | Choisir un document, un mode d'extraction et un mode de validation. | Extrait le texte, le découpe et lance l'analyse côté serveur. | L'analyse arrive à son terme, sans avertissement ignoré. |
| Comprendre | Lire la synthèse de chaque carte et ses sources. | Propose des concepts, une qualification et, si détectées, des règles. | Le sens du document est conservé. |
| Décider | Valider, corriger ou mettre à revoir. | Enregistre la décision et actualise la connaissance exploitable. | Seuls les éléments retenus et validés alimentent le graphe principal. |
| Relier | Examiner les rapprochements utiles. | Propose des liens et aide à rechercher une cible. | Le lien a le bon sens et les bons concepts aux deux extrémités. |
| Contrôler Echo | Examiner les nouveautés et les contrôles. | Compare à la référence et exécute les contrôles pris en charge. | Reconnu, nouveau, incertain et non conforme restent distincts. |
| Exporter | Choisir le format et, pour Echo, préparer le bilan. | Produit les fichiers et leur traçabilité. | Le destinataire peut comprendre le lot sans rouvrir ECUME. |

**Ne pas confondre :**
- Une **carte** est une proposition de compréhension d'un passage documentaire.
- Un **concept** est un élément de connaissance pouvant être partagé entre plusieurs cartes.
- Un **lien** exprime une relation entre deux concepts.
- Un **référentiel Echo** est une référence de comparaison, pas le graphe métier ECUME.
- **Valider une carte**, **valider une correspondance Echo** et **réussir un contrôle SHACL** sont trois décisions ou résultats différents.

## 2. Admin : préparer l'analyse

| Champ ou action | Signification et rôle d'ECUME | Votre vérification |
| --- | --- | --- |
| Fournisseur | Choisit Ollama local ou une API externe compatible avec le protocole attendu. | Une API externe reçoit le contenu envoyé pour analyse : vérifier les règles de confidentialité de votre organisation. |
| URL Ollama | Adresse du service Ollama, habituellement `http://localhost:11434`. | Ollama doit être lancé et joignable depuis le backend. |
| Modèle Ollama | Nom exact du modèle à appeler. | Il doit être disponible localement. Ce champ ne télécharge pas le modèle. |
| URL API | Adresse du service externe. | Utiliser l'adresse attendue par votre fournisseur. |
| Modèle API | Identifiant du modèle distant. | Le compte doit avoir accès à ce modèle. |
| Clé API | Secret permettant d'appeler le service. | Ne pas le partager dans une capture, un export public ou Git. |
| Analyse heuristique si le LLM échoue | Autorise une solution de secours plus simple lorsque le modèle échoue. | Ce résultat n'a pas la même qualité qu'une analyse LLM ; le relire attentivement. |
| Enregistrer | Sauvegarde les champs de configuration. | Enregistrer avant de tester : le bouton Tester utilise la configuration enregistrée. |
| Tester | Vérifie le service configuré. | Un test réussi ne garantit ni la qualité métier, ni la réussite d'un gros document, ni l'usage du GPU. |

La RAZ et la suppression de concepts sont expliquées en section 11. Elles ne servent pas à réparer une connexion LLM.

## 3. Référentiels : préparer Echo

Cette étape est facultative pour produire des cartes métier, mais nécessaire pour les comparer à Echo.

### Importer les trois couches

1. Importer `Echo_C2.owl.ttl`.
2. Conserver le même référentiel cible et importer `Echo_C2.voc.ttl`.
3. Conserver encore cette cible et importer `Echo_C2.shacl.ttl`.
4. Cliquer sur **Examiner** pour vérifier le profil.

| Champ ou indicateur | Ce que cela signifie | Ce que fait ECUME / point à vérifier |
| --- | --- | --- |
| Référentiel Echo | Ensemble logique auquel rattacher le fichier. | Regroupe les couches. Pour un autre domaine ou une autre version, choisir une nouvelle cible plutôt que mélanger les fichiers. |
| Nouveau / regrouper par nom | Création ou regroupement automatique selon le nom du fichier. | Les noms de type `Nom.owl.ttl`, `Nom.voc.ttl`, `Nom.shacl.ttl` facilitent le regroupement. Vérifier la cible obtenue. |
| Couche : automatique | ECUME tente de reconnaître la nature du contenu. | La déclaration ne transforme pas un fichier mal structuré en couche valide. |
| OWL : modèle conceptuel | Classes, propriétés et structure formelle. | Sert à proposer un positionnement, sans raisonnement OWL complet. |
| VOC : vocabulaire métier | Termes de référence, variantes et synonymes. | Sert à reconnaître les expressions utilisées dans les documents. |
| SHACL : règles de contrôle | Propriétés attendues et contraintes de structuration. | ECUME applique seulement le sous-ensemble qu'il sait interpréter. |
| Plusieurs couches | Le fichier mélange plusieurs types de contenu. | Examiner le profil réellement détecté. |
| Importer la copie | Lit une copie locale du fichier. | Les originaux ne sont jamais modifiés. Un fichier identique sur la même cible n'est pas dupliqué. |
| Actif pour les correspondances | Rend la référence disponible pour les rapprochements. | Désactiver n'efface pas vos anciennes décisions. |
| Profil suffisant / partiel / insuffisant | Appréciation de l'exploitabilité du paquet. | Ce n'est pas une certification de sa justesse sémantique. Lire les avertissements. |
| Couche non fournie / importée / partiellement comprise / insuffisante | État propre à chaque couche. | Un fichier lu n'implique pas que tout son contenu soit exploitable. |
| Classes / propriétés | Catégories et relations ou attributs formels détectés dans OWL. | Ce ne sont pas les concepts créés à partir de vos documents. |
| Termes | Entrées du vocabulaire reconnu. | Vérifier les libellés, définitions et autres noms. |
| Formes interprétées / non interprétées | Règles SHACL prises en charge ou non. | Une forme non interprétée ne doit pas être considérée comme un contrôle réussi. |
| Langue / version | Métadonnées détectées dans la référence. | Une absence de valeur signifie qu'elle n'a pas été détectée. |
| Rechercher dans les termes | Recherche dans la copie importée. | Vérifier un terme représentatif avant d'analyser un document. |
| URI / namespace / types | Identité technique stable et classement des termes. | À conserver pour les échanges ; deux libellés identiques peuvent avoir des URI différentes. |
| Supprimer la copie | Retire la référence locale et ses correspondances. | Ne supprime pas les connaissances métier ECUME ni le fichier original. |

Limites actuelles : Turtle ou RDF/XML, pas tous les dialectes OWL ; 5 Mio et 100 000 triplets par fichier ; 12 fichiers par paquet. Pas de remplacement automatique de version ni de suppression individuelle d'un fichier du paquet.

## 4. Import : charger et piloter un document

### Les choix avant lancement

| Champ ou action | Ce que fait ECUME | Ce que vous décidez |
| --- | --- | --- |
| Choisir un fichier | Accepte `.txt`, `.md`, `.pdf`, `.docx`. | Fournir un document dont le texte est exploitable. Un PDF scanné n'est pas rendu lisible par OCR dans ce MVP. |
| Mode d'extraction : Sobre | Privilégie les éléments essentiels et limite le bruit. | Choix conseillé pour commencer. |
| Équilibré | Demande davantage de contexte et de concepts. | Accepter un travail de revue plus important. |
| Exhaustif | Demande une extraction plus détaillée. | Plus de propositions à vérifier, sans garantie de tout extraire. |
| Mode de validation | Détermine quelles propositions peuvent être validées automatiquement. | Ne pas confondre avec le mode d'extraction, qui règle la quantité et la sélection. |
| Conserver les sources | Conserve le fichier original et le texte extrait. | Utile pour la recette et les relances. |
| Purger après analyse réussie | Supprime ensuite la source et le texte intégral, pas la connaissance produite. | Les extraits utiles, cartes, concepts et liens restent. Il faudra refournir le fichier pour une nouvelle analyse. |
| Importer et analyser | Transfère le fichier puis lance le traitement serveur. | Attendre que le transfert soit terminé et que l'analyse soit lancée avant de quitter cette vue. |

### Comprendre les modes de validation

Les pourcentages ci-dessous sont les **valeurs recommandées**, pas une affirmation sur vos réglages actuels. Les valeurs réellement enregistrées sont visibles dans **Réglages avancés** et ne sont pas changées par cette fiche.

| Mode | Comportement actuel, en l'absence de blocage |
| --- | --- |
| Strict | Toutes les cartes demandent une décision humaine. |
| Assisté | Auto-validation à partir du seuil haut, recommandé à 90 %. Entre le seuil bas et le seuil haut : à revoir. En dessous du seuil bas : validation utilisateur nécessaire. |
| Automatique | Auto-validation à partir du seuil bas, recommandé à 60 %. En dessous : à revoir. Ce mode est donc moins exigeant qu'Assisté. |

Une carte sans score numérique n'est jamais auto-validée artificiellement. Un niveau inconnu, une catégorie non qualifiée, une description absente ou des incertitudes peuvent empêcher l'auto-validation même avec un score élevé.

| Commande ou champ | Effet |
| --- | --- |
| Niveau d'exigence : Recommandé / Personnalisé | Indique si les seuils sont 90 % / 60 % ou différents. |
| Changer le mode | Dans Import : choisit le mode de cette analyse. Dans le panneau global : enregistre le choix pour les prochaines analyses. |
| Auto-validation en Assisté (%) | Seuil haut utilisé en mode Assisté. |
| À revoir / Automatique (%) | Seuil bas, également utilisé pour l'auto-validation en mode Automatique. |
| Rétablir 90 % / 60 % | Remplace explicitement les seuils personnalisés. Ne cliquer que si vous le souhaitez. |
| Appliquer aux cartes non décidées | Action explicite sur la sélection existante, sans rappeler le LLM. Fournit un bilan ; préserve les décisions humaines et les cartes sans score. |

### Pendant l'analyse

ECUME prépare le texte, le découpe en parties, analyse chaque partie avec le modèle, consolide les résultats puis enregistre les propositions. Le contexte des références actives aide le modèle lorsqu'il est disponible.

| Indicateur | Lecture correcte |
| --- | --- |
| En attente | Travail enregistré, pas encore en cours d'exécution. |
| En cours | Travail exécuté côté backend. Vous pouvez changer d'onglet dans ECUME une fois l'analyse lancée. |
| Partie X / Y | Avancement dans le texte découpé, pas dans le nombre de pages du fichier. |
| Pourcentage | Indicateur d'étapes, pas une estimation fiable du temps restant. Une partie peut être beaucoup plus lente qu'une autre. |
| Analyse terminée | Le traitement a réussi ; les propositions restent à contrôler selon le mode choisi. |
| Analyse interrompue ou échouée | Lire le détail, corriger le problème puis relancer si la source est disponible. |

**Le backend et le fournisseur LLM doivent rester en fonctionnement.** Changer d'onglet n'est pas arrêter l'application. Un redémarrage du PC ou du backend peut interrompre le traitement. La présence d'une image n'implique pas que celle-ci soit analysée visuellement.

### Documents importés et menu Actions

| Champ ou action | Utilité et effet |
| --- | --- |
| Nom et date | Identifient le document et son import. |
| État de l'analyse | État du dernier traitement associé au document. |
| Mode de la dernière analyse | Rappelle le mode réellement utilisé, ou signale un historique non enregistré. |
| Nombre de cartes et statuts | Compte les cartes, pas le nombre de concepts uniques. Les auto-validées sont distinguées. |
| Source conservée / purgée / absente / purge à terminer | Décrit le stockage de la source, indépendamment du statut des connaissances. |
| Ouvrir les cartes | Ouvre les cartes de ce document avec le filtre documentaire. |
| Relancer | Lance une nouvelle analyse avec les choix courants ; ne remet pas la base à zéro et conserve les propositions existantes. |
| Fournir à nouveau le fichier | Restaure la source du document. Utiliser le fichier d'origine, pas une nouvelle version différente. |
| Purger la source | Après confirmation, retire l'original et le texte intégral ; conserve cartes, concepts, liens et extraits courts. |
| Conservation | Modifie la politique de ce document pour la prochaine analyse réussie. |
| Supprimer | Ouvre une action destructive distincte, décrite en section 11. |

La carte manuelle, proposée notamment après une erreur d'analyse, utilise les mêmes notions : thème, effet principal, description, objets, actions, conditions et tâches. Les listes sont saisies séparées par des virgules ; elle ne bénéficie pas pour autant d'une analyse automatique fiable.

## 5. Cartes : comprendre avant de valider

### Lire et corriger les champs métier

| Champ | Sens | ECUME prépare | Vous vérifiez |
| --- | --- | --- | --- |
| Thème | Sujet qui regroupe la proposition. | Un intitulé de contexte. | Le thème aide à retrouver la carte sans devenir une phrase trop longue. |
| Effet principal / intitulé | Résultat ou idée centrale de la carte. | Un libellé synthétique. | Il décrit le bon sens, pas seulement un mot présent dans le document. |
| Synthèse / description | Ce qu'ECUME a compris du passage. | Une reformulation. | Elle conserve les règles, limites, conditions et exceptions utiles. |
| Catégorie métier | Nature de l'élément principal. | Une proposition de qualification. | La catégorie répond à « de quoi s'agit-il ? ». Voir le tableau suivant. |
| Niveau | Échelle à laquelle l'idée s'applique. | Stratégique, opératif, tactique, opérateur ou à préciser. | Ne pas confondre niveau et importance. |
| Justification | Pourquoi cette qualification a été proposée. | Une explication courte. | C'est une explication à examiner, pas une preuve. |
| Confiance / score métier | Estimation de fiabilité de la compréhension. | Un score numérique lorsqu'il existe ; certains anciens champs restent qualitatifs. | 90 % n'est pas une garantie statistique de vérité. Une absence n'est pas un zéro. |
| Source / extrait | Passage documentaire permettant le contrôle. | Un extrait court et une référence documentaire. | Le passage soutient réellement la proposition et n'a pas perdu sa portée. |
| Avertissements / points à éclaircir | Difficultés ou ambiguïtés de l'analyse. | Des alertes. | Les résoudre avant une validation irréfléchie. |

### Catégories métier

| Catégorie | Question simple |
| --- | --- |
| Résultat recherché | Quel résultat veut-on obtenir ? |
| Objectif haut niveau | Quelle finalité générale poursuit-on ? |
| Capacité à obtenir | Que doit-on être capable de faire ? |
| Action / activité | Que fait-on pour produire le résultat ? |
| Chose métier | Sur quel objet, sujet ou élément agit-on ? |
| Donnée manipulée | Quelle information utilise-t-on ou produit-on ? |
| Condition / règle / contrainte | Dans quel cas, selon quelle obligation ou limite ? |
| Tâche concrète | Quelle opération précise réalise-t-on ? |
| Acteur / organisation | Qui agit ou porte une responsabilité ? |
| Rôle tenu | Dans quelle fonction cet acteur intervient-il ? |
| Service rendu | Quel service est fourni à un utilisateur ou métier ? |
| Service applicatif | Quel service est fourni par une application ? |
| Élément technique | Quel composant technique participe au fonctionnement ? |
| Non qualifié | La nature reste à préciser ; ne pas inventer une catégorie. |

### Niveaux

| Niveau | Lecture |
| --- | --- |
| Stratégique | Finalité générale, orientation ou ambition. |
| Opératif | Effet attendu dans la conduite d'une mission ou d'un processus. |
| Tactique | Effet local, coordination ou décision proche de l'action. |
| Opérateur | Exécution concrète par une personne, une équipe ou un système. |
| À préciser | Le contexte ne permet pas encore de trancher. |

### Concepts associés et importance locale

| Champ | Sens et traitement |
| --- | --- |
| Objet / « Ce dont on parle » | Élément sur lequel porte la carte. |
| Action / « Ce qui est fait » | Activité décrite dans le passage. |
| Condition / « Dans quel cas » | Condition ou contrainte d'application. |
| Tâche / « Réalisé concrètement » | Opération précise à effectuer. |
| Principal | Élément central dans cette carte. Il peut devenir visible dans le graphe validé. |
| Secondaire | Contexte utile, non retenu par défaut dans le graphe des nouvelles extractions gérées. |
| Faible intérêt | Proposition jugée peu utile pour la capitalisation principale. |
| Ignoré | Élément laissé de côté dans ce contexte. |
| Retenir ce concept | Rend l'élément actif pour cette carte et remet la carte à revoir. Il faut la revalider. |
| Importance / saillance | Utilité locale pour comprendre la carte, différente de la confiance. Un même concept peut être principal ici et secondaire ailleurs. |
| Extraits et règles en détail | Préservent des informations sans créer systématiquement un nœud de graphe pour chacune. |

Les anciennes cartes ne sont pas silencieusement reclassées selon ces règles. Un concept partagé peut rester présent grâce à d'autres cartes même si vous le retirez de celle-ci.

### Les boutons de décision

| Action | Effet attendu |
| --- | --- |
| Valider | Confirme la compréhension métier. La carte quitte la file des cartes à traiter et devient consultable dans les vues validées, selon les filtres. |
| Corriger | Ouvre la modification. Enregistrer une correction demande ensuite de revoir/valider la carte. |
| À revoir | Conserve la proposition, mais ne la considère pas comme connaissance validée dans le périmètre principal. |
| Voir sources | Affiche l'extrait disponible pour contrôler la compréhension. |
| Voir graphe | Permet de consulter le contexte relationnel. |
| Accepter sans rattachement | Accepte explicitement un élément isolé, exportable sans inventer de relation. |
| Rejeter | Écarte la proposition de la connaissance validée sans confondre ce choix avec une suppression physique. |
| Fusionner avec | Réunit des cartes portant réellement sur la même idée. Vérifier les sources, règles et rattachements après fusion. |
| Rattacher à un concept | Relie la carte à un concept existant ; ce n'est pas une fusion des identités. |
| Supprimer | Action destructive. Lire la confirmation et le périmètre, en particulier pour les concepts partagés. |

## 6. Règles métier : contrôler les détails qui comptent

Une règle peut rester dans la carte sans devenir un concept distinct. Son statut suit celui de la carte, pas une validation parallèle.

| Champ | Signification | Vérification à faire |
| --- | --- | --- |
| Intitulé | Nom court de la règle. | Il permet de la distinguer des autres. |
| Description | Formulation complète. | Préserve notamment minimum/maximum, interdiction/autorisation, obligation/possibilité. |
| Type de règle | Qualification structurée conservée si disponible. | Ne remplace pas la lecture de la description ; pas nécessairement affiché dans le formulaire courant. |
| Valeur | Nombre ou valeur explicitement mentionné. | Vérifier décimales, comparateur et contexte. Le comparateur peut rester dans la description. |
| Unité | Unité associée à la valeur. | Ne pas confondre mètres, pourcentage, durée, surface, etc. |
| Condition | Cas dans lequel la règle s'applique. | Une condition omise peut changer entièrement le sens. |
| Exception | Cas qui limite ou déroge à la règle. | Ne pas généraliser une exception ni l'oublier. |
| Source | Extrait permettant de vérifier la formulation. | Retrouver la valeur et sa portée dans le texte. |
| Corriger / Enregistrer et revoir | Enregistre la correction et remet la carte à revoir. | Revalider après contrôle ; elle sort du lot principal jusqu'à validation. |

Pour les nouvelles réponses structurées, ECUME vérifie la présence de certains extraits et valeurs dans le texte disponible. Cela détecte des incohérences mais ne démontre pas la justesse de l'interprétation. Après purge du texte, les possibilités de revérification sont réduites.

## 7. Rapprochements et liens entre concepts

Deux usages distincts : un rapprochement interne crée un lien entre concepts ECUME ; une correspondance Echo relie un concept ECUME à un terme de référence.

### Rapprochements internes

| Champ ou action | Lecture / effet |
| --- | --- |
| Source | Concept de départ du lien, et non document source. |
| Cible | Concept vers lequel pointe le lien. |
| Relation | Sens exprimé entre source et cible. Toujours lire « source → relation → cible ». |
| Justification | Pourquoi ce lien est proposé. |
| Confiance | Estimation propre au lien, distincte de celle de la carte. |
| Importants | Quelques propositions mises en avant ; le reste reste accessible replié. |
| Fiables (estimation) | Proposition complète avec score élevé ; reste à examiner, pas une certitude. |
| À vérifier | Proposition incertaine ou demandant une décision. |
| Incomplets | Une extrémité ou la relation n'est pas exploitable ; Accepter n'est pas proposé. |
| Ignorés / rejetés | Décisions conservées pour ne pas reproposer silencieusement le même choix. |
| Acceptés | Liens déjà décidés, humainement ou par la politique automatique dans les cas admissibles. |
| Choisir une cible / Corriger le lien | Répare la proposition ; une correction n'est pas à elle seule son acceptation. |
| Accepter | Enregistre le lien si la proposition est exploitable. |
| Recherche de cible | Montre un nombre limité de résultats avec contexte. Affiner le texte et les filtres plutôt que choisir le premier nom similaire. |

Valider une carte n'accepte pas tous ses liens. L'auto-validation de certains liens exige notamment une cible valide, un score suffisant et l'absence d'alternative ambiguë.

| Relation | Lecture pédagogique |
| --- | --- |
| contribue à | A participe à l'obtention de B. |
| se décompose en | A contient une composante B ; parent vers enfant. |
| concerne | A porte sur B. |
| nécessite | A a besoin de B. |
| déclenche | A provoque ou initie B. |
| proche de | A est voisin de B, sans identité affirmée. |
| équivalent à | A et B ont un sens considéré équivalent ; ce choix ne fusionne pas automatiquement les nœuds. |

Même pour « proche de » ou « équivalent à », les exports possèdent une source et une cible : ne pas supposer que toutes les applications créeront une relation inverse.

### Correspondances Echo

| Champ ou résultat | Signification |
| --- | --- |
| Éléments déjà reconnus | Un nom ou synonyme exact et unique a été reconnu dans la couche cible. La reconnaissance est lexicale, pas une preuve générale d'équivalence. |
| Référentiel / terme cible | Référence choisie et terme auquel le concept pourrait correspondre. Lire sa définition. |
| Même sens | Correspondance candidate d'équivalence de sens. |
| Proche | Sens voisins, sans équivalence certaine. |
| Référence plus générale | Le terme Echo est plus large que le concept ECUME. |
| Référence plus précise | Le terme Echo est plus spécifique que le concept ECUME. |
| Lié | Association pertinente sans identité ni hiérarchie affirmée. |
| Score / raison | Force et justification du rapprochement proposé ; pas la confiance de validation métier. |
| À confirmer | Candidat sans confirmation humaine. Même un élément reconnu peut conserver ce statut. |
| Correspondance validée | Vous avez confirmé la correspondance et son sens. |
| À revoir / Pas le bon concept | Doute ou refus enregistré, sans supprimer le concept métier. |
| Concept modifié depuis la décision | La correspondance est devenue ancienne et doit être revérifiée. Son historique n'est pas effacé. |
| Chercher des correspondances | Recherche des candidats sans écraser vos décisions humaines. |
| Nouveauté proposée | Élément sans reconnaissance suffisante, à examiner avant enrichissement. Ne prouve pas son absence de toute l'ontologie. |

Le résumé automatique Echo est calculé pour les cartes validées et lors de la préparation du lot. L'absence de correspondance n'empêche pas une connaissance métier d'être utile et validée.

## 8. Contrôles SHACL : lire le bilan sans surinterpréter

ECUME construit une représentation de travail puis vérifie les contraintes simples qu'il sait projeter : présence, nombre de valeurs, type, classe attendue, liste de valeurs ou motif notamment.

| Résultat | Ce qu'il signifie | Action utile |
| --- | --- | --- |
| Conforme au contrôle | Les contraintes effectivement vérifiées sont satisfaites. | Ne pas en déduire que toutes les règles métier ou toutes les contraintes Echo ont été vérifiées. |
| À compléter | Des informations ou conditions du contrôle demandent une attention. | Lire le message et compléter lorsque le document permet de le faire. |
| Non conforme | Une contrainte vérifiée n'est pas satisfaite. | Corriger la donnée ou examiner la pertinence du rapprochement et du contrôle. |
| Non vérifiable | ECUME ne sait pas appliquer le contrôle dans ce cas, ou son exécution n'a pas abouti. | Ne pas transformer ce résultat en conformité. Prévoir une revue externe si nécessaire. |

Un contrôle SHACL ne valide pas automatiquement une carte et ne la supprime pas. Les chemins complexes, contraintes non prises en charge et propriétés non projetables restent des limites explicites. Le moteur n'exécute pas de code ou de requête SPARQL provenant des fichiers importés.

## 9. Graphe, cartes validées et orphelins

| Élément | Utilisation |
| --- | --- |
| Vue graphe | Comprendre les concepts et leurs relations acceptées. |
| Vue cartes / hiérarchie | Relire la connaissance validée dans une présentation plus structurée. |
| Recherche / filtres | Restreindre ce qui est affiché ; ne supprime pas les éléments masqués. |
| Interroger le graphe | Retrouver un concept, ses relations directes et les cartes associées. |
| Sélection d'un concept | Lire sa description, son statut et son contexte avant d'agir. |
| Modifier | Correction explicite. Contrôler ensuite les statuts et les conséquences sur les cartes et liens. |
| Orphelin | Concept sans rattachement pertinent dans le périmètre contrôlé ; pas forcément une erreur. |
| Modifier / rattacher | Qualifier l'orphelin et choisir, si justifié, une cible et une relation. |
| Accepter sans rattachement | Assume explicitement l'isolement ; ne fabrique pas de lien pour faire disparaître une alerte. |

Le graphe principal privilégie les concepts principaux validés, les secondaires explicitement retenus et les liens acceptés. Une carte à revoir n'efface pas un concept partagé encore validé par une autre carte.

## 10. Exports : choisir le bon fichier

### Deux périmètres ECUME à distinguer

| Export | Usage et précaution |
| --- | --- |
| Graphe validé : JSON | Réutilisation structurée de la connaissance validée avec ses métadonnées. |
| Archive JSON complète | Périmètre plus large, avec les propositions et états conservés par l'export. Ne pas la confondre avec le seul graphe validé ni avec une sauvegarde intégrale du dossier `data/`. |
| JSON-LD | Données liées avec identifiants et contexte ; ne constitue pas à lui seul une ontologie complète. |
| CSV | Inspection tabulaire des nœuds et relations. |
| Memgraph | Échange vers le graphe de propriétés ; suivre les instructions du paquet et du guide exports. |
| RDF/SKOS | Export générique disponible ; à distinguer d'un export conforme au modèle Echo, non livré dans ce lot. |
| ArchiMate JSON | Représentation intermédiaire de mappings candidats ; pas un fichier ArchiMate Exchange XML. |

### Lot d'enrichissement Echo

1. Choisir le **référentiel cible**.
2. Cliquer sur **Préparer le bilan**.
3. Lire les compteurs et avertissements.
4. Télécharger **JSON Echo complet** et **ZIP de contrôle**.
5. Faire relire avant toute intégration dans l'outil de référence.

| Élément du lot | Ce qu'il contient / signifie |
| --- | --- |
| Profil cible | Référence et couches utilisées pour établir le lot. |
| Éléments reconnus | Concepts rapprochés de l'existant selon les règles de reconnaissance. |
| Nouveaux concepts proposés | Nouveautés présumées, pas ajouts autorisés automatiquement. |
| Termes VOC proposés | Enrichissements possibles du vocabulaire métier. |
| Synonymes / définitions proposés | Enrichissements d'une cible existante, sous les conditions de confirmation prévues. |
| Règles métier | Valeurs, unités, conditions, exceptions et sources structurées. Le compteur ne prouve pas que chaque règle est absente d'Echo. |
| Alignements OWL / VOC / SHACL | Positionnements et correspondances proposés, avec leur statut. |
| Contrôles et éléments à revoir | Résultats, avertissements et limites à traiter. |
| Sources | Fiches documentaires et extraits utiles, pas l'intégralité des fichiers originaux. |
| ZIP CSV | Tableaux de contrôle humain, JSON et rapport ; le JSON reste la représentation complète. |

**ECUME ne réimporte rien automatiquement dans Echo et ne modifie jamais les fichiers sources.** Un lot exportable n'est pas un lot autorisé à entrer sans contrôle dans la référence centrale.

## 11. Purger, rejeter, supprimer : choisir la bonne action

| Votre objectif | Action | Ce qui reste / vigilance |
| --- | --- | --- |
| Libérer l'espace occupé par un original | Purger la source | Cartes, concepts, liens, extraits utiles et traçabilité conservés. |
| Ne pas retenir une proposition métier | Rejeter la carte | Décision conservée ; ne la traite plus comme validée. |
| Ne pas retenir un lien | Ignorer / rejeter le rapprochement | Les concepts ne sont pas fusionnés ni supprimés. |
| Retirer un document de la bibliothèque | Supprimer le document, sans option connaissance | Source purgée ; connaissances conservées avec une référence documentaire historique. Confirmation `SUPPRIMER`. |
| Supprimer aussi sa connaissance propre | Cocher la suppression des cartes/concepts exclusivement associés | Des éléments validés peuvent être supprimés ; les concepts partagés sont protégés. Confirmation supplémentaire `SUPPRIMER LES CONNAISSANCES`. |
| Retirer une référence Echo locale | Supprimer la copie | Connaissance ECUME et original conservés ; correspondances de cette référence retirées. |
| Supprimer globalement un concept | Admin : Concepts en base → Supprimer | Ce n'est pas un retrait local d'une carte. Examiner l'impact sur ses liens et usages avant confirmation. |
| Repartir de zéro pour un test | Admin : RAZ complète | Efface la connaissance, les documents, travaux, historique et données de l'atelier Echo. Action destructive, pas un simple rafraîchissement. |

La RAZ exige `RESET ECUME` puis une confirmation. Les options « Supprimer aussi les fichiers importés » et « Supprimer aussi les exports » concernent les fichiers locaux gérés par l'application. **Décocher ces options ne conserve pas la base de connaissances.** Faire une sauvegarde du dossier `data/`, application arrêtée, avant toute RAZ utile à des tests.

## 12. Annexe : comprendre les champs avancés et les exports

Ces champs sont principalement destinés à la traçabilité et à la réutilisation. Il n'est pas nécessaire de les renseigner tous à la main.

| Champ | Sens |
| --- | --- |
| `id` | Identifiant stable de l'objet ; le nom seul n'est pas une identité fiable. |
| `label` / `canonical_label` | Libellé affiché / forme de référence lorsqu'elle est fournie par l'export. |
| `aliases` | Autres noms associés au concept ; vérifier leur équivalence de sens. |
| `type` | Rôle structurel historique : effet, objet, action, condition, tâche ou thème. Distinct de la catégorie métier. |
| `business_category` | Qualification métier lisible, par exemple capacité ou acteur. |
| `level` | Niveau stratégique, opératif, tactique, opérateur ou inconnu. |
| `description` / `business_justification` | Explication du concept / raison de sa qualification. |
| `confidence` / `business_confidence` | Estimation qualitative / score numérique métier s'il existe. |
| `status` / `validation_status` | État de fonctionnement conservé pour la compatibilité : proposé, accepté, à confirmer, rejeté, etc. |
| `business_validation_status` | Nature de la décision métier : auto-validé, validé par l'utilisateur, corrigé, à revoir, rejeté ou à valider. « Corrigé » ne suffit pas à conclure « validé ». |
| `validation_decision` | Origine, date, seuils, raisons et blocages de la décision lorsque disponibles. |
| `importance` / `salience_score` | Importance locale dans une carte / score associé ; distinct de la fiabilité. |
| `source_ids` / `source_titles` | Identifiants et noms des documents qui étayent l'élément. |
| `source_excerpt` | Court passage justificatif conservé. |
| `source_card_ids` / `graph_node_ids` | Liens entre les cartes et les concepts du graphe. |
| `source_node_id` / `target_node_id` | Extrémités orientées d'une relation. Ne désignent pas les documents sources. |
| `relation_type` | Nature du lien ; son sens se lit de source vers cible. |
| `created_at` / `updated_at` | Dates de création et de dernière modification, pas dates de publication des documents. |
| `origin` / historique | Origine des opérations : analyse, utilisateur, correction, fusion, etc., selon les traces disponibles. |
| `content_hash` | Empreinte permettant de reconnaître un contenu identique ; ni résumé ni preuve d'authenticité. |
| `metadata` / `extraction_details` | Informations complémentaires : contexte, propositions, règles, sources et détails de traitement. |
| `target_uri` | Identifiant du terme dans la référence externe. |
| `match_type` / `score` / `reason` | Type, force et explication d'une correspondance ; différents d'un lien métier interne. |
| `stale` | Correspondance à revérifier car son contexte a changé depuis la proposition ou la décision. |
| `archimate_mapping` | Objet candidat contenant framework, version, couche, élément, confiance, justification et statut. |
| `archimate_mapping_status` | État propre à la traduction architecturale ; valider le métier ne valide pas automatiquement ArchiMate. |
| `ontology_mapping_status` | Indicateur historique général. Les correspondances détaillées Echo portent leurs propres statuts et décisions. |
| `alignment_ready` | Profil exploitable pour proposer des correspondances, pas autorisation de réimport. |
| `rdf_export_ready` | Aptitude à un export RDF adapté à Echo ; reste fausse dans ce lot. |
| `ready_for_automatic_import` | Reste faux : la revue humaine du lot est nécessaire. |

**Point de vigilance de cette version :** certains anciens textes du panneau avancé d'une carte annoncent encore les référentiels comme une fonction future. Pour le lot actuel, utiliser les blocs Echo dédiés, la page Référentiels et le bilan d'export. Cette fiche ne modifie pas ces libellés.

## 13. Fiche de suivi à remplir pendant votre recette

| Information | À renseigner |
| --- | --- |
| Date / personne | |
| Document analysé | |
| Référentiel Echo et version | |
| Modèle utilisé | |
| Mode d'extraction | |
| Mode de validation et seuils réellement affichés | |
| Conservation de la source | |
| Nombre de cartes produites / validées / à revoir | |
| Anomalies et cartes concernées | |
| Export produit / destinataire | |

- [ ] Le service LLM a été testé après enregistrement de sa configuration.
- [ ] Les couches Echo sont rattachées au bon référentiel et leurs limites sont connues.
- [ ] Le transfert puis l'analyse du document sont terminés.
- [ ] J'ai contrôlé des cartes contre leurs extraits, pas uniquement contre leur score.
- [ ] J'ai vérifié les valeurs, unités, conditions et exceptions importantes.
- [ ] Les concepts secondaires retenus ont une utilité réelle.
- [ ] Les liens ont une source, une cible et un sens corrects.
- [ ] Les concepts isolés sont rattachés ou explicitement assumés.
- [ ] Les correspondances évidentes et les cas ambigus sont distingués.
- [ ] J'ai lu les contrôles non conformes et non vérifiables.
- [ ] J'ai revalidé les cartes corrigées que je veux inclure dans le lot principal.
- [ ] J'ai ouvert les exports et retrouvé les définitions, relations et sources utiles.
- [ ] Je n'ai pas confondu purge de source, suppression de connaissance et RAZ.
- [ ] Le lot Echo sera revu humainement avant intégration externe.

## Pour aller plus loin

- [Recette détaillée du MVP Echo](echo-owl-voc-shacl.md)
- [Formats d'export et import Memgraph](exports.md)
- [Extraction et réduction du bruit](extraction.md)

Guide établi à partir des pages et composants frontend actuels, des types partagés et du service backend de validation. Il décrit le comportement implémenté, sans constituer une garantie de qualité du modèle sur vos documents.
