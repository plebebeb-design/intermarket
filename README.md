# Intermarket Pra-Sesi

Dashboard statis yang diperbarui otomatis oleh GitHub Actions dan dilayani lewat GitHub Pages. Semua gratis, tanpa server.

## Cara kerja

1. GitHub Actions menjalankan `scripts/fetch_data.py` pukul 07:30 WIB (sebelum sesi IDX, setelah penutupan AS) dan 16:30 WIB (setelah IDX tutup), Senin sampai Jumat.
2. Skrip mengambil harga dari Yahoo Finance (yfinance) dan data kredit serta suku bunga dari FRED. Tidak perlu API key.
3. Hasilnya disimpan ke `data/latest.json` dan `data/history.json`, lalu di-commit ke repositori.
4. Situs diterbitkan ke GitHub Pages. `index.html` membaca file JSON itu.

## Pemasangan (sekali saja)

1. Buat repositori **publik** baru di GitHub, misalnya `intermarket`. Pages pada repositori privat memerlukan paket berbayar.
2. Unggah seluruh isi folder ini ke cabang `main`. Pastikan folder `.github/workflows/` ikut terunggah.
3. Buka **Settings → Pages**. Pada *Source* pilih **GitHub Actions**.
4. Buka **Settings → Actions → General → Workflow permissions**, pilih **Read and write permissions**, lalu simpan.
5. Buka tab **Actions**, pilih workflow *Perbarui data dan terbitkan dashboard*, klik **Run workflow**.
6. Setelah hijau (sekitar 1–2 menit), alamat dashboard muncul di langkah *Terbitkan*, biasanya `https://NAMA-ANDA.github.io/intermarket/`.

Setelah itu workflow berjalan sendiri sesuai jadwal.

## Mencoba tampilan di komputer sendiri

```bash
pip install -r requirements.txt
python scripts/fetch_data.py --demo    # data sintetis, tanpa internet
python -m http.server 8000
```

Buka `http://localhost:8000`. Halaman akan menampilkan spanduk "Data demo". Jalankan tanpa `--demo` untuk data asli.

## Yang perlu diisi manual

| File | Isi | Kapan |
|---|---|---|
| `data/flows.json` | Arus dana mingguan (Lipper/EPFR dari berita Reuters) | Jumat atau Sabtu |
| `data/events.json` | Kalender acara pekan ini (waktu WIB) | Senin pagi |

Arus dana global tidak tersedia gratis lewat API, jadi dua file ini ditulis tangan. Setiap commit pada dua file itu memicu penerbitan ulang otomatis.

## Menambah atau mengganti instrumen

Edit daftar `ASSETS` di `scripts/fetch_data.py`. Setiap baris berisi id, nama, grup, sumber (`yf` atau `fred`), simbol, dan jenis (`price` atau `yield`). Atur jumlah desimal di `DP`. Simbol Yahoo bisa dicari di finance.yahoo.com. Daftar seri FRED ada di fred.stlouisfed.org.

## Aturan sinyal

Terdapat di `build_signals()` dan juga tampil di setiap kartu pada dashboard. Contoh: VIX di atas 28 dihitung tekanan, UST 10 tahun naik lebih dari 15 bp dalam 5 hari dihitung tekanan. Ubah ambang batasnya sesuai gaya Anda. Aturan ini cara cepat merangkum kondisi, bukan prediksi.

## Batasan yang perlu diketahui

- **yfinance tidak resmi.** Yahoo bisa membatasi atau mengubah format kapan saja. Kalau ada instrumen gagal, dashboard menampilkan daftarnya di bagian atas dan baris itu tidak muncul. Jika lebih dari 40% instrumen gagal, data lama tidak ditimpa.
- **Jadwal GitHub bisa tertunda** belasan menit pada jam sibuk. Dashboard memberi peringatan bila data lebih tua dari 36 jam.
- **FRED terlambat satu hari** untuk UST 2 tahun, kurva imbal hasil, dan spread kredit. Kolom *Per* di papan harga menunjukkan tanggal tiap data.
- **Tidak ada yield SBN Indonesia, net sell asing, atau data IDX resmi.** Tidak ada API gratis yang stabil untuk itu. Satu-satunya petunjuk Indonesia otomatis adalah IHSG, USD/IDR, dan EIDO (ETF yang diperdagangkan di AS setelah IHSG tutup).
- **Bukan saran investasi.** Cocokkan angka dengan broker atau terminal sebelum bertransaksi.
