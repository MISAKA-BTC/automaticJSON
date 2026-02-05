import json
import re
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox

# ---- 置換ロジック ----

def looks_like_solana_address(s: str) -> bool:
    """
    厳密ではなく“事故防止”の軽いチェック。
    Solanaのbase58はだいたい 32〜44文字。記号はほぼ出ない。
    """
    s = s.strip()
    if not (32 <= len(s) <= 44):
        return False
    # base58-ish（厳密ではないが安全側）
    if not re.fullmatch(r"[1-9A-HJ-NP-Za-km-z]+", s):
        return False
    return True

def replace_worker_part(user_value: str, sol_addr: str) -> str:
    """
    XMRig pools[].user の "XMR_WALLET.WORKER" の WORKER 部分だけ置換。
    最後の '.' より右側だけを sol_addr にする。
    """
    if not isinstance(user_value, str) or "." not in user_value:
        return user_value
    prefix, _ = user_value.rsplit(".", 1)
    return f"{prefix}.{sol_addr}"

def patch_xmrig_config_inplace(in_path: Path, sol_addr: str) -> tuple[int, Path, Path, list[str]]:
    """
    in_path: config.json（これを上書き）
    sol_addr: 新しいSolanaアドレス

    戻り値: (変更したpool数, 保存先パス(=in_path), バックアップパス, プレビュー文字列リスト)
    """
    data = json.loads(in_path.read_text(encoding="utf-8"))
    pools = data.get("pools", None)
    if not isinstance(pools, list) or len(pools) == 0:
        raise ValueError('このJSONに "pools": [...] が見つかりませんでした。')

    preview = []
    changed = 0

    for i, pool in enumerate(pools):
        if not isinstance(pool, dict):
            continue
        u = pool.get("user")
        if isinstance(u, str) and "." in u:
            new_u = replace_worker_part(u, sol_addr)
            if new_u != u:
                pool["user"] = new_u
                changed += 1
                preview.append(f"pools[{i}].user: ...{u[-28:]}  →  ...{new_u[-28:]}")

    # --- 上書き前にバックアップ作成（安全） ---
    backup_path = in_path.with_suffix(in_path.suffix + ".bak")  # config.json.bak
    backup_path.write_text(in_path.read_text(encoding="utf-8"), encoding="utf-8")

    # --- 上書き保存（ファイル名は常にconfig.json） ---
    in_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    return changed, in_path, backup_path, preview


# ---- GUI ----

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("XMRig config.json - Solana worker 書き換え（上書き保存）")
        self.geometry("760x420")

        self.in_path: Path | None = None

        # ファイル選択
        frm_top = tk.Frame(self)
        frm_top.pack(fill="x", padx=12, pady=12)

        tk.Button(frm_top, text="config.json を選ぶ", command=self.pick_file, width=18).pack(side="left")
        self.lbl_file = tk.Label(frm_top, text="未選択", anchor="w")
        self.lbl_file.pack(side="left", padx=10, fill="x", expand=True)

        # Solana入力
        frm_mid = tk.Frame(self)
        frm_mid.pack(fill="x", padx=12, pady=8)

        tk.Label(frm_mid, text="Solana アドレス（worker に入れる値）").pack(anchor="w")
        self.ent_solana = tk.Entry(frm_mid, font=("Arial", 12))
        self.ent_solana.pack(fill="x", pady=6)

        # ボタン
        frm_btn = tk.Frame(self)
        frm_btn.pack(fill="x", padx=12, pady=8)

        tk.Button(frm_btn, text="プレビュー確認", command=self.preview, width=14).pack(side="left")
        tk.Button(frm_btn, text="上書き保存（config.json）", command=self.save, width=24).pack(side="left", padx=10)

        self.lbl_status = tk.Label(frm_btn, text="", anchor="w", fg="gray")
        self.lbl_status.pack(side="left", padx=10, fill="x", expand=True)

        # プレビュー表示
        tk.Label(self, text="変更プレビュー（末尾だけ表示）", fg="gray").pack(anchor="w", padx=12)
        self.txt_preview = tk.Text(self, height=12, wrap="none")
        self.txt_preview.pack(fill="both", expand=True, padx=12, pady=8)

        # 注意書き
        tk.Label(
            self,
            text="※ XMRウォレット側（最後の . より左）は変更しません。※ 上書き前に config.json.bak を自動作成します。",
            fg="gray"
        ).pack(anchor="w", padx=12, pady=4)

    def pick_file(self):
        path = filedialog.askopenfilename(
            title="XMRig config.json を選択",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")]
        )
        if not path:
            return
        self.in_path = Path(path)
        self.lbl_file.config(text=str(self.in_path))
        self.lbl_status.config(text="ファイル選択OK")
        self.txt_preview.delete("1.0", tk.END)

    def preview(self):
        self.txt_preview.delete("1.0", tk.END)

        if not self.in_path:
            messagebox.showwarning("注意", "先に config.json を選んでください。")
            return

        sol = self.ent_solana.get().strip()
        if not sol:
            messagebox.showwarning("注意", "Solana アドレスを入力してください。")
            return

        if not looks_like_solana_address(sol):
            if not messagebox.askyesno("確認", "Solanaアドレスっぽくないかも。続行しますか？"):
                return

        try:
            data = json.loads(self.in_path.read_text(encoding="utf-8"))
            pools = data.get("pools", [])
            lines = []
            count = 0
            for i, pool in enumerate(pools if isinstance(pools, list) else []):
                if isinstance(pool, dict) and isinstance(pool.get("user"), str):
                    u = pool["user"]
                    if "." in u:
                        new_u = replace_worker_part(u, sol)
                        if new_u != u:
                            count += 1
                            lines.append(f"pools[{i}].user: ...{u[-28:]}  →  ...{new_u[-28:]}")
            if count == 0:
                self.txt_preview.insert(tk.END, "変更対象が見つかりませんでした。\n（pools[].user に '.' が無い、または pools が無い可能性）\n")
            else:
                self.txt_preview.insert(tk.END, "\n".join(lines) + "\n")
            self.lbl_status.config(text=f"プレビュー: 変更対象 {count} 件")
        except Exception as e:
            messagebox.showerror("エラー", f"プレビュー失敗:\n{e}")

    def save(self):
        self.txt_preview.delete("1.0", tk.END)

        if not self.in_path:
            messagebox.showwarning("注意", "先に config.json を選んでください。")
            return

        sol = self.ent_solana.get().strip()
        if not sol:
            messagebox.showwarning("注意", "Solana アドレスを入力してください。")
            return

        if not looks_like_solana_address(sol):
            if not messagebox.askyesno("確認", "Solanaアドレスっぽくないかも。続行しますか？"):
                return

        # 上書きは危険なので最終確認
        if not messagebox.askyesno("最終確認", f"次のファイルを上書きしますか？\n\n{self.in_path}\n\n（自動で .bak を作成します）"):
            return

        try:
            changed, out_path, backup_path, preview = patch_xmrig_config_inplace(self.in_path, sol)

            if changed == 0:
                messagebox.showwarning(
                    "注意",
                    "変更対象が0件でした。\n保存は行いましたが、内容が変わっていない可能性があります。"
                )

            self.txt_preview.insert(tk.END, "\n".join(preview) + ("\n" if preview else ""))
            self.lbl_status.config(text=f"上書き保存完了: {changed}件（backup: {backup_path.name}）")
            messagebox.showinfo("完了", f"{changed}件を書き換えて上書き保存しました:\n{out_path}\n\nバックアップ:\n{backup_path}")
        except Exception as e:
            messagebox.showerror("エラー", f"保存失敗:\n{e}")


if __name__ == "__main__":
    App().mainloop()
