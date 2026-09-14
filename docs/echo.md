# Atelier Echo

ECUME prepare des propositions ; le referentiel Echo reste la reference centrale.
Le flux est : reference locale -> concepts metier valides -> correspondances ->
lot d'enrichissement -> controle humain et reimport dans l'outil externe.
Aucun nom de metier ou namespace Marine n'est impose.

## Installation et reprise

Depuis la racine du projet, serveurs arretes :

```powershell
powershell -ExecutionPolicy Bypass -File scripts\install-deps.ps1 -WithDev
powershell -ExecutionPolicy Bypass -File scripts\start-ecume.ps1
```

RDFLib et defusedxml sont les seules nouvelles dependances directes. Le script
verifie les versions Python deja installees avant de demander une installation.
Au demarrage, SQLite ajoute quatre tables : `reference_repositories`,
`reference_terms`, `reference_relations`, `echo_mappings`. Le profil est un JSON
dans `reference_repositories`, pas une ontologie ECUME supplementaire.
Ces ajouts ne reclassent aucune carte et ne changent aucun seuil de validation.
Sauvegarder `data/` localement avant une mise a jour, sans l'ajouter a Git.

## Importer une reference

Dans **Referentiels**, choisir un fichier local. Formats acceptes : `.ttl` Turtle,
`.rdf` ou `.owl` en RDF/XML ou Turtle. OWL/XML et la syntaxe fonctionnelle OWL
ne sont pas pris en charge. Limites MVP : 5 Mio et 100 000 triplets.

ECUME conserve une copie binaire immuable dans sa base locale, son empreinte
SHA-256, le nom du fichier et les termes/relations interpretes dans des tables
separees de la connaissance metier. Reimporter les memes octets retrouve la meme
copie, sans effacer ses decisions. Une autre version constitue une autre copie :
desactiver l'ancienne pour ne plus l'utiliser lors des recherches.

**Examiner** montre un echantillon de huit termes, avec recherche et pagination.
Le profil indique langue, version, quantites et avertissements ; namespaces,
proprietes RDF et URI sont dans les details techniques replies.
Le francais est prioritaire pour le libelle d'affichage, puis un libelle sans
langue, puis les autres langues. Les autres libelles et proprietes restent conserves.

Le profil reconnait les libelles RDFS/SKOS, synonymes, definitions, commentaires,
classes OWL et relations courantes. Il reste explicitement partiel si certaines
structures ne sont pas interpretees. Aucune convention de nommage n'est inventee.
Les structures anonymes restent dans la copie source, sans raisonnement OWL.

L'import ne suit pas `owl:imports`, ne telecharge aucun namespace et interdit
les lectures de fichiers ou acces reseau pendant le parsing. DTD et entites XML
sont refuses. Ces precautions suivent les [considerations de securite RDFLib](https://rdflib.readthedocs.io/en/stable/security_considerations/).

Desactiver une copie conserve ses mappings. La supprimer demande `SUPPRIMER` :
cela retire cette copie et ses alignements locaux, pas les cartes, concepts ou
liens metier. Les decisions supprimees restent tracees dans l'historique.
La RAZ administrative inclut aussi ces tables.

## Decider les correspondances

Depuis une carte validee, ouvrir **Correspondances possibles dans les referentiels
Echo**, puis lancer explicitement la recherche. On peut changer de concept dans
la carte avec une recherche limitee a huit resultats par page. La page
Referentiels propose aussi une recherche sur l'ensemble des concepts valides.

Le moteur utilise noms, synonymes, proximite lexicale, definitions, categorie et
contexte documentaire. Il propose au maximum cinq candidats par concept et
referentiel. Il ne s'agit ni d'une probabilite calibree ni d'une preuve de sens
identique. Les relations voisines, embeddings et raisonnements ne sont pas utilises.
Un lot de plus de 250 000 comparaisons est refuse avec une invitation a rechercher
concept par concept. Les recherches sont synchrones et bornees dans ce MVP.

| Decision | Sens depuis le concept ECUME vers la cible Echo |
| --- | --- |
| Meme sens | `exactMatch`, equivalence semantique confirmee par la personne. |
| Proche | `closeMatch`, sens voisin sans affirmer une equivalence. |
| Reference plus generale | `broadMatch`, la cible Echo est plus generale. |
| Reference plus precise | `narrowMatch`, la cible Echo est plus precise. |
| Lie | `relatedMatch`, association sans hierarchie. |

Les statuts sont independants : candidat, valide, a revoir, rejete. Plusieurs
mappings sont possibles. Une recherche ne remplace jamais une decision humaine.
Si le concept change ensuite, le mapping est signale comme ancien/a reverifier ;
il faut reconfirmer pour qu'il serve a un enrichissement. Sans mapping, le concept
conserve sa valeur et sa validation metier. Echo et ArchiMate restent separes.

## Relire le lot d'enrichissement

Dans un referentiel, ouvrir **Lot d'enrichissement Echo** et choisir JSON ou CSV.
Le JSON est la sortie de reference pour une integration future. Le ZIP CSV sert
a la revue humaine et contient egalement le JSON complet, un rapport de controle
JSON et un README expliquant les colonnes.

| Fichier | Contenu |
| --- | --- |
| JSON Echo | Metadonnees, reference cible et empreinte, profil, concepts, mappings, enrichissements, relations, sources, cartes de preuve, elements a revoir et rapport. |
| `echo_new_concepts.csv` | Concepts hors enrichissements exacts, avec leur classification : nouveau, alignement, doublon possible ou a revoir. Seules les lignes `new_concept` sont proposees comme nouvelles. |
| `echo_enrichments.csv` | Synonymes et definitions supplementaires proposes pour une cible dont le mapping exact a ete valide humainement. |
| `echo_mappings.csv` | Alignements candidats/valides et correspondances a revoir, distingues par statut effectif, avec type, score, justification et cible. |
| `echo_relations.csv` | Relations metier acceptees dont les deux extremites sont exportables, proposees pour revue externe. |
| `echo_warnings.csv` | Limites et avertissements a prendre en compte avant reimport. |

Les concepts ont des URI stables `urn:ecume:node:{id}`. Les URI Echo existantes
sont conservees telles quelles : ECUME ne fabrique pas de nouvelles URI dans le
namespace central. Chaque relation se lit **source -> type -> cible**. Les labels,
descriptions et sources rendent ce sens lisible sans rouvrir ECUME. Une relation
ECUME n'est pas automatiquement traduite en propriete Echo : cette traduction
reste a decider. Le profil transporte les conventions detectees pour ce travail.

L'export principal exclut les concepts rejetes/a revoir, les faibles elements non
retenus et les liens incomplets ou non acceptes. Les elements secondaires doivent
avoir ete explicitement retenus. Les anciennes donnees sans importance locale
restent identifiees `legacy_unclassified`, sans nettoyage automatique.
Les correspondances exactes non validees sont des doublons possibles, pas des
enrichissements autorises. Mappings rejetes exclus ; mappings a revoir ou devenus
anciens dans la section de revue, pas comme alignements valides.

Le rapport compte les nouveaux concepts, enrichissements, mappings par type et
statut, non-alignes, doublons possibles et exclusions. Toute sortie porte
`ready_for_automatic_import: false` : un outil externe doit controler le lot.
Une definition proposee est une information supplementaire, jamais une instruction
de remplacer silencieusement la definition de reference.

Sources documentaires, extraits courts, regles et importance locale sont conserves,
meme apres purge d'une source metier. Le texte integral et les chemins des fichiers
originaux ne sont pas inclus. Les CSV sont UTF-8 avec BOM ; valeurs structurees en
JSON et cellules ressemblant a des formules protegees par une apostrophe. Le JSON
conserve les valeurs originales sans cette protection de presentation.

## Limites de ce lot

- Aucun referentiel Marine reel n'a encore ete fourni pour la recette.
- Les conventions personnalisees peuvent necessiter une adaptation explicite.
- JSON et CSV sont des paquets de propositions, pas des formats d'import universels.
- JSON-LD et TTL Echo attendent une validation du profil et du JSON sur la reference reelle.
- Pas de modification de la source, import distant, connecteur, raisonneur, PPTX ou ArchiMate XML.
- Les exports graphe ECUME/JSON-LD/Memgraph et ArchiMate JSON existants restent distincts.

Les sources, bases, copies de recette et exports restent dans `data/`, exclu de
Git. Les fichiers RDF/TTL/OWL sont egalement ignores par defaut pour eviter une
publication accidentelle ; les petits exemples des tests sont des chaines synthetiques.
