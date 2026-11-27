"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import styles from "./research.module.css";

type Track = {
  id: string;
  display_name: string;
  genres: { name: string; weight: number }[];
  tags: string[];
  training_plays: number;
  can_stream: false;
};
type Page = { total: number; items: Track[] };
type User = { id: string; history_size: number };
type Recommendation = {
  track_id: string;
  track: Track;
  score: number;
  reason: "collaborative" | "content" | "popularity";
  components: { collaborative: number; content: number; popularity: number };
};
type Info = { tracks: number; users: number; train_pairs: number; genres: string[] };

// Dedicated local demo endpoint: never uses a Supabase key or the production API.
const API = (process.env.NEXT_PUBLIC_RESEARCH_API_BASE_URL || "http://127.0.0.1:8001").replace(/\/$/, "");
const reasons = {
  collaborative: "Người có lịch sử nghe tương tự",
  content: "Phù hợp thể loại và lựa chọn của bạn",
  popularity: "Phổ biến trong dữ liệu huấn luyện",
};

async function request<T>(path: string, body?: object, signal?: AbortSignal): Promise<T> {
  const response = await fetch(`${API}/api/v1/research${path}`, {
    method: body ? "POST" : "GET",
    headers: body ? { "Content-Type": "application/json" } : undefined,
    body: body ? JSON.stringify(body) : undefined,
    signal,
  });
  if (!response.ok) throw new Error(`Không thể tải dữ liệu (${response.status}). Kiểm tra backend demo và artifact local.`);
  return response.json() as Promise<T>;
}

function TrackCard({ track, onSelect, recommendation }: {
  track: Track;
  onSelect: (track: Track) => void;
  recommendation?: Recommendation;
}) {
  return (
    <article className={styles.card}>
      <p className={styles.id}>MUSIC4ALL · {track.id}</p>
      <h3>{track.display_name}</h3>
      <div className={styles.tags}>
        {track.genres.slice(0, 4).map((genre) => <span key={genre.name}>{genre.name}</span>)}
      </div>
      <p className={styles.muted}>{track.tags.slice(0, 5).join(" · ") || "Chưa có tags"}</p>
      <p>{track.training_plays.toLocaleString("vi-VN")} lượt nghe trong tập train</p>
      {recommendation && (
        <details>
          <summary>{reasons[recommendation.reason]} · {recommendation.score.toFixed(3)}</summary>
          <p>Điểm thành phần trước khi áp trọng số:</p>
          <p>Cộng tác {recommendation.components.collaborative.toFixed(3)} · Nội dung {recommendation.components.content.toFixed(3)} · Phổ biến {recommendation.components.popularity.toFixed(3)}</p>
        </details>
      )}
      <button type="button" onClick={() => onSelect(track)}>Chọn làm ngữ cảnh gợi ý</button>
    </article>
  );
}

export default function ResearchPage() {
  const [info, setInfo] = useState<Info | null>(null);
  const [users, setUsers] = useState<User[]>([]);
  const [user, setUser] = useState("");
  const [genre, setGenre] = useState("");
  const [query, setQuery] = useState("");
  const [activeQuery, setActiveQuery] = useState("");
  const [offset, setOffset] = useState(0);
  const [page, setPage] = useState<Page>({ total: 0, items: [] });
  const [recent, setRecent] = useState<Track[]>([]);
  const [history, setHistory] = useState<{ track: Track; plays: number }[]>([]);
  const [recommendations, setRecommendations] = useState<Recommendation[]>([]);
  const [error, setError] = useState("");
  const [catalogError, setCatalogError] = useState("");
  const [recommendationError, setRecommendationError] = useState("");
  const [loading, setLoading] = useState(true);
  const [ranking, setRanking] = useState(false);

  useEffect(() => {
    const controller = new AbortController();
    Promise.all([
      request<Info>("/info", undefined, controller.signal),
      request<{ items: User[] }>("/users?limit=100", undefined, controller.signal),
    ]).then(([metadata, people]) => {
      setInfo(metadata);
      setUsers(people.items);
    }).catch((e: Error) => { if (!controller.signal.aborted) setError(e.message); });
    return () => controller.abort();
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setCatalogError("");
    const params = new URLSearchParams({ query: activeQuery, offset: String(offset), limit: "12" });
    if (genre) params.set("genre", genre);
    request<Page>(`/tracks?${params}`, undefined, controller.signal)
      .then(setPage)
      .catch((e: Error) => { if (!controller.signal.aborted) setCatalogError(e.message); })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [activeQuery, genre, offset]);

  useEffect(() => {
    const controller = new AbortController();
    setHistory([]);
    if (user) {
      request<{ track: Track; plays: number }[]>(`/users/${encodeURIComponent(user)}/history`, undefined, controller.signal)
        .then(setHistory)
        .catch((e: Error) => { if (!controller.signal.aborted) setError(e.message); });
    }
    return () => controller.abort();
  }, [user]);

  useEffect(() => {
    if (!info) return;
    const controller = new AbortController();
    setRanking(true);
    setRecommendationError("");
    setRecommendations([]);
    request<{ items: Recommendation[] }>("/recommendations", {
      user_id: user || null,
      genres: genre ? [genre] : [],
      recent_track_ids: recent.map((track) => track.id),
      limit: 10,
    }, controller.signal).then((result) => setRecommendations(result.items))
      .catch((e: Error) => { if (!controller.signal.aborted) setRecommendationError(e.message); })
      .finally(() => { if (!controller.signal.aborted) setRanking(false); });
    return () => controller.abort();
  }, [info, user, genre, recent]);

  function selectTrack(track: Track) {
    setRecent((current) => [track, ...current.filter((item) => item.id !== track.id)].slice(0, 5));
  }
  function search(event: FormEvent) {
    event.preventDefault();
    setOffset(0);
    setActiveQuery(query.trim());
  }

  return (
    <main className={styles.page} lang="vi">
      <header className={styles.header}>
        <div><p className="eyebrow">Music4All-Onion · Local research demo</p><h1>Khám phá gu âm nhạc.</h1></div>
        <Link href="/">Trang chủ</Link>
      </header>
      <p className={styles.intro}>Tra cứu theo ID, thể loại và tags. Bộ dữ liệu hiện có chưa chứa tên bài, nghệ sĩ hoặc audio; Track + ID là nhãn hiển thị. Lựa chọn bên dưới chỉ mô phỏng ngữ cảnh, chưa phải một lượt nghe.</p>
      {info && <div className={styles.stats}><span><strong>{info.tracks.toLocaleString("vi-VN")}</strong> bài</span><span><strong>{info.users.toLocaleString("vi-VN")}</strong> người dùng nghiên cứu</span><span><strong>{info.train_pairs.toLocaleString("vi-VN")}</strong> cặp tương tác train</span></div>}
      {error && <p role="alert" className="state-panel">{error} <button onClick={() => window.location.reload()}>Thử lại</button></p>}
      <section className={styles.controls} aria-label="Tùy chỉnh sở thích">
        <label>Hồ sơ lịch sử mẫu<select value={user} onChange={(e) => { setUser(e.target.value); setRecent([]); }}><option value="">Người mới · chưa có lịch sử</option>{users.map((person) => <option key={person.id} value={person.id}>User {person.id} · {person.history_size} bài</option>)}</select></label>
        <label>Thể loại quan tâm<select value={genre} onChange={(e) => { setGenre(e.target.value); setOffset(0); }}><option value="">Tất cả thể loại</option>{info?.genres.map((name) => <option key={name} value={name}>{name}</option>)}</select></label>
      </section>
      {history.length > 0 && <details className={styles.history}><summary>Lịch sử train của user {user}: {history.length} bài</summary>{history.slice(0, 10).map((row) => <p key={row.track.id}>{row.track.display_name} · {row.plays} lượt · {row.track.genres.slice(0, 2).map((g) => g.name).join(", ")}</p>)}<p>Hiển thị tối đa 10 bài, theo số lượt nghe; dữ liệu chưa có thứ tự thời gian.</p></details>}
      {recent.length > 0 && <div className={styles.context}>Ngữ cảnh vừa chọn: {recent.map((t) => t.id).join(" → ")} <button onClick={() => setRecent([])}>Xóa ngữ cảnh</button></div>}
      <section aria-label="Gợi ý cá nhân hóa" aria-busy={ranking}>
        <div className={styles.sectionTitle}><h2>Gợi ý dành cho bạn</h2><span>Item-kNN + genre cosine + popularity</span></div>
        <p className={styles.muted}>Chọn hồ sơ hoặc thể loại để cá nhân hóa. Khi chưa có tín hiệu, hệ thống dùng độ phổ biến lịch sử. Bài đã nằm trong lịch sử hoặc ngữ cảnh được loại khỏi kết quả.</p>
        {ranking && <p role="status">Đang tính gợi ý…</p>}
        {recommendationError && <p role="alert">{recommendationError}</p>}
        {!ranking && !recommendationError && info && recommendations.length === 0 && <p>Không còn ứng viên phù hợp trong tập demo.</p>}
        <div className={styles.grid}>{recommendations.map((row) => <TrackCard key={row.track_id} track={row.track} recommendation={row} onSelect={selectTrack} />)}</div>
      </section>
      <section aria-label="Tra cứu catalog">
        <div className={styles.sectionTitle}><h2>Tra cứu dữ liệu</h2><span>{page.total.toLocaleString("vi-VN")} kết quả</span></div>
        <form className="search-form" onSubmit={search} role="search"><label htmlFor="research-search">ID bài hát, thể loại hoặc tag</label><div className="search-controls"><input id="research-search" type="search" value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Ví dụ: rock, pop, electronic hoặc track ID" /><button type="submit">Tìm kiếm</button></div></form>
        {loading && <p role="status">Đang tải catalog…</p>}
        {catalogError && <p role="alert">{catalogError}</p>}
        {!loading && !catalogError && page.items.length === 0 && <p>Không tìm thấy bài phù hợp.</p>}
        {!loading && !catalogError && <div className={styles.grid}>{page.items.map((track) => <TrackCard key={track.id} track={track} onSelect={selectTrack} />)}</div>}
        <nav className={styles.pagination} aria-label="Phân trang"><button disabled={loading || offset === 0} onClick={() => setOffset(Math.max(0, offset - 12))}>Trước</button><span>Trang {Math.floor(offset / 12) + 1}</span><button disabled={loading || offset + 12 >= page.total} onClick={() => setOffset(offset + 12)}>Sau</button></nav>
      </section>
    </main>
  );
}
