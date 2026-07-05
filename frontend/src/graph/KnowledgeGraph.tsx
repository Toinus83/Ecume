import cytoscape, { Core } from "cytoscape";
import { useEffect, useRef } from "react";
import type { GraphPayload, KnowledgeNode } from "../types";

interface Props {
  graph: GraphPayload | null;
  onSelect: (node: KnowledgeNode) => void;
}

export default function KnowledgeGraph({ graph, onSelect }: Props) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const cyRef = useRef<Core | null>(null);

  useEffect(() => {
    if (!containerRef.current || !graph) return;
    cyRef.current?.destroy();
    const nodeIds = new Set(graph.nodes.map((node) => node.id));
    const safeEdges = graph.edges.filter(
      (edge) => nodeIds.has(edge.source_node_id) && nodeIds.has(edge.target_node_id)
    );
    const cy = cytoscape({
      container: containerRef.current,
      elements: [
        ...graph.nodes.map((node) => ({ data: { ...node, id: node.id } })),
        ...safeEdges.map((edge) => ({
          data: {
            ...edge,
            id: edge.id,
            source: edge.source_node_id,
            target: edge.target_node_id
          }
        }))
      ],
      style: [
        {
          selector: "node",
          style: {
            label: "data(label)",
            "background-color": "#2563eb",
            color: "#1f2937",
            "font-size": "11px",
            "text-wrap": "wrap",
            "text-max-width": "120px",
            "border-width": "2px",
            "border-color": "#ffffff"
          }
        },
        { selector: 'node[type = "effect"]', style: { "background-color": "#0f766e", width: "42px", height: "42px" } },
        { selector: 'node[type = "object"]', style: { "background-color": "#7c3aed" } },
        { selector: 'node[type = "action"]', style: { "background-color": "#c2410c" } },
        { selector: 'node[type = "condition"]', style: { "background-color": "#b45309" } },
        { selector: 'node[type = "task"]', style: { "background-color": "#0369a1" } },
        { selector: 'node[status = "accepted_orphan"]', style: { "border-color": "#f59e0b", "border-width": "4px" } },
        {
          selector: "edge",
          style: {
            width: "2px",
            "line-color": "#94a3b8",
            "target-arrow-color": "#94a3b8",
            "target-arrow-shape": "triangle",
            "curve-style": "bezier",
            label: "data(label)",
            "font-size": "9px",
            color: "#475569",
            "text-background-color": "#ffffff",
            "text-background-opacity": 0.85
          }
        }
      ],
      layout: { name: "cose", animate: true, fit: true, padding: 40 }
    });
    cy.on("tap", "node", (event) => onSelect(event.target.data() as KnowledgeNode));
    cyRef.current = cy;
    return () => cy.destroy();
  }, [graph, onSelect]);

  return <div className="graph-canvas" ref={containerRef} />;
}
