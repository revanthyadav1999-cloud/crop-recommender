"use client";
import { useState } from "react";

export default function Home() {
  const [soilType, setSoilType] = useState("loamy");
  const [ph, setPh] = useState(6.5);
  const [lat, setLat] = useState(17.3850);
  const [lon, setLon] = useState(78.4867);
  const [results, setResults] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function handleSubmit(e) {
    e.preventDefault();
    setLoading(true);
    setError("");
    setResults([]);

    try {
      const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "http://127.0.0.1:8000";
      const res = await fetch(`${API_BASE}/recommend`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          lat: Number(lat),
          lon: Number(lon),
          soil_type: soilType,
          ph: Number(ph),
        }),
      });
      if (!res.ok) {
        throw new Error("Server returned " + res.status);
      }
      const data = await res.json();
      setResults(data);
    } catch (err) {
      setError(err && err.message ? err.message : "Something went wrong");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="min-h-screen bg-gradient-to-b from-green-50 to-emerald-50">
      <div className="max-w-xl mx-auto p-6">
        <h1 className="text-3xl font-bold text-emerald-800 mb-2">🌾 Crop Recommendation</h1>
        <p className="text-emerald-700 mb-6">Enter your soil and location to get the best crops for your field.</p>

        <form onSubmit={handleSubmit} className="bg-white rounded-2xl shadow p-5 space-y-4">
          <div>
            <label className="block text-sm font-medium mb-1">Soil Type</label>
            <select
              value={soilType}
              onChange={(e) => setSoilType(e.target.value)}
              className="w-full border rounded-lg p-2 focus:outline-none focus:ring-2 focus:ring-emerald-400"
            >
              <option value="loamy">Loamy</option>
              <option value="sandy">Sandy</option>
              <option value="clay">Clay</option>
            </select>
          </div>

          <div>
            <label className="block text-sm font-medium mb-1">Soil pH</label>
            <input
              type="number"
              step="0.1"
              value={ph}
              onChange={(e) => setPh(e.target.value)}
              className="w-full border rounded-lg p-2 focus:outline-none focus:ring-2 focus:ring-emerald-400"
            />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-sm font-medium mb-1">Latitude</label>
              <input
                type="number"
                step="0.0001"
                value={lat}
                onChange={(e) => setLat(e.target.value)}
                className="w-full border rounded-lg p-2 focus:outline-none focus:ring-2 focus:ring-emerald-400"
              />
            </div>
            <div>
              <label className="block text-sm font-medium mb-1">Longitude</label>
              <input
                type="number"
                step="0.0001"
                value={lon}
                onChange={(e) => setLon(e.target.value)}
                className="w-full border rounded-lg p-2 focus:outline-none focus:ring-2 focus:ring-emerald-400"
              />
            </div>
          </div>

          <button
            type="submit"
            disabled={loading}
            className="w-full bg-emerald-600 hover:bg-emerald-700 text-white font-medium py-2.5 rounded-xl transition disabled:opacity-60"
          >
            {loading ? "Calculating..." : "Get Recommendations"}
          </button>

          {error ? (
            <div className="text-red-600 text-sm bg-red-50 border border-red-200 p-2 rounded-lg">{error}</div>
          ) : null}
        </form>

        {results && results.length > 0 ? (
          <div className="mt-6 bg-white rounded-2xl shadow p-4">
            <h2 className="text-xl font-semibold mb-3">Top Crops</h2>
            <ul className="space-y-2">
              {results.map(function (r, i) {
                return (
                  <li key={i} className="flex items-center justify-between border rounded-lg p-2">
                    <span className="font-medium">{r.crop}</span>
                    <span className="text-emerald-700 font-semibold">{r.score}</span>
                  </li>
                );
              })}
            </ul>
          </div>
        ) : null}
      </div>
    </main>
  );
}
