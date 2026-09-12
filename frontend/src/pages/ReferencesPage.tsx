import { FileUp, RefreshCcw, ToggleLeft } from "lucide-react";

export default function ReferencesPage() {
  return (
    <section className="page-stack">
      <div className="section-title">
        <h2>Referentiels</h2>
        <span>prepare pour le prochain lot</span>
      </div>

      <div className="panel">
        <h3>Ontologies / referentiels metier</h3>
        <p className="description">
          Cette entree est prevue pour charger des fichiers locaux RDF, TTL ou OWL et rapprocher les concepts ECUME des referentiels disponibles.
        </p>
        <div className="disabled-upload">
          <strong>Import local RDF / TTL / OWL</strong>
          <p className="quiet-note">
            Le moteur de lecture et de rapprochement sera ajoute dans un lot dedie. Les cartes peuvent deja conserver le statut des concepts non alignes.
          </p>
          <button disabled><FileUp size={16} />Importer un referentiel</button>
        </div>
      </div>

      <div className="reference-grid">
        <article className="reference-card">
          <span>Sources locales</span>
          <p>Fichiers .rdf, .ttl et .owl fournis manuellement par l'utilisateur.</p>
        </article>
        <article className="reference-card">
          <span>Activation</span>
          <p>Chaque referentiel pourra etre active ou desactive pour les rapprochements.</p>
        </article>
        <article className="reference-card">
          <span>Rapprochement</span>
          <p>ECUME pourra relancer la recherche sur les concepts non alignes ou a mapper plus tard.</p>
        </article>
      </div>

      <div className="panel">
        <h3>Fonctions cible</h3>
        <div className="link-list">
          <article>
            <p><FileUp size={14} /> Importer un fichier local RDF, TTL ou OWL.</p>
          </article>
          <article>
            <p><ToggleLeft size={14} /> Activer ou desactiver un referentiel.</p>
          </article>
          <article>
            <p><RefreshCcw size={14} /> Relancer le rapprochement sur les concepts non alignes.</p>
          </article>
        </div>
      </div>
    </section>
  );
}
