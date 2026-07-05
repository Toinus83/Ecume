import { Trash2 } from "lucide-react";

interface Props {
  title: string;
  items: string[];
  empty?: string;
  onDelete?: (item: string, index: number) => void;
  disabled?: boolean;
}

export default function TagList({ title, items, empty = "Aucun", onDelete, disabled }: Props) {
  return (
    <div className="tag-group">
      <span>{title}</span>
      <div>
        {items.length === 0 ? (
          <em>{empty}</em>
        ) : items.map((item, index) => (
          <b key={`${item}-${index}`} className={onDelete ? "tag-with-action" : ""}>
            {item}
            {onDelete && (
              <button
                type="button"
                className="tag-delete"
                onClick={() => onDelete(item, index)}
                disabled={disabled}
                title="Supprimer ce concept"
              >
                <Trash2 size={12} />
              </button>
            )}
          </b>
        ))}
      </div>
    </div>
  );
}
