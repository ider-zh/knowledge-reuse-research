import { useMemo, useState } from "react";

export type Column<T> = {
  id: string;
  label: string;
  value: (row: T) => string | number | boolean | null | undefined;
  render?: (row: T) => React.ReactNode;
  align?: "left" | "right";
};

type Props<T> = {
  rows: T[];
  columns: Column<T>[];
  initialSort?: string;
  initialDescending?: boolean;
  searchPlaceholder?: string;
};

function compare(left: unknown, right: unknown): number {
  if (left == null) return 1;
  if (right == null) return -1;
  if (typeof left === "number" && typeof right === "number") return left - right;
  return String(left).localeCompare(String(right), "zh-CN");
}

export function DataTable<T>({
  rows,
  columns,
  initialSort,
  initialDescending = true,
  searchPlaceholder = "搜索当前发布样本…",
}: Props<T>) {
  const [query, setQuery] = useState("");
  const [sortId, setSortId] = useState(initialSort ?? columns[0]?.id ?? "");
  const [descending, setDescending] = useState(initialDescending);
  const [page, setPage] = useState(0);
  const pageSize = 25;

  const filtered = useMemo(() => {
    const needle = query.trim().toLocaleLowerCase();
    const selected = needle
      ? rows.filter((row) =>
          columns.some((column) =>
            String(column.value(row) ?? "")
              .toLocaleLowerCase()
              .includes(needle),
          ),
        )
      : rows;
    const sortColumn = columns.find((column) => column.id === sortId);
    if (!sortColumn) return selected;
    return [...selected].sort((left, right) => {
      const order = compare(sortColumn.value(left), sortColumn.value(right));
      return descending ? -order : order;
    });
  }, [columns, descending, query, rows, sortId]);

  const pageCount = Math.max(1, Math.ceil(filtered.length / pageSize));
  const safePage = Math.min(page, pageCount - 1);
  const visible = filtered.slice(safePage * pageSize, (safePage + 1) * pageSize);

  const sort = (id: string) => {
    if (id === sortId) setDescending((value) => !value);
    else {
      setSortId(id);
      setDescending(true);
    }
    setPage(0);
  };

  return (
    <div className="data-table-shell">
      <div className="table-tools">
        <label>
          <span className="sr-only">搜索</span>
          <input
            value={query}
            onChange={(event) => {
              setQuery(event.target.value);
              setPage(0);
            }}
            placeholder={searchPlaceholder}
          />
        </label>
        <span>
          命中 {filtered.length.toLocaleString()} / 已发布 {rows.length.toLocaleString()}
        </span>
      </div>
      <div className="table-scroll">
        <table>
          <thead>
            <tr>
              {columns.map((column) => (
                <th key={column.id} className={column.align === "right" ? "numeric" : ""}>
                  <button onClick={() => sort(column.id)}>
                    {column.label}
                    {sortId === column.id ? (descending ? " ↓" : " ↑") : ""}
                  </button>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {visible.map((row, rowIndex) => (
              <tr key={rowIndex}>
                {columns.map((column) => (
                  <td key={column.id} className={column.align === "right" ? "numeric" : ""}>
                    {column.render?.(row) ?? String(column.value(row) ?? "—")}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="pagination">
        <button disabled={safePage === 0} onClick={() => setPage(safePage - 1)}>
          ← 上一页
        </button>
        <span>
          {safePage + 1} / {pageCount}
        </span>
        <button disabled={safePage + 1 >= pageCount} onClick={() => setPage(safePage + 1)}>
          下一页 →
        </button>
      </div>
    </div>
  );
}
