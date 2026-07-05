import { Download } from "lucide-react";
import { api } from "../api/client";

const exports = [
  ["json", "Exporter JSON"],
  ["jsonld", "Exporter JSON-LD"],
  ["csv", "Exporter CSV"],
  ["memgraph", "Exporter Memgraph"],
  ["rdf-skos", "Exporter RDF/SKOS"]
] as const;

export default function ExportPage() {
  return (
    <section className="page-stack">
      <div className="export-grid">
        {exports.map(([kind, label]) => (
          <a className="export-button" href={api.exportUrl(kind)} key={kind}>
            <Download size={18} />
            <span>{label}</span>
          </a>
        ))}
      </div>
    </section>
  );
}
