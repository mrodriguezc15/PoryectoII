"""
core/eda.py
Motor de Análisis Exploratorio de Datos (EDA).
Genera estadísticas, gráficos y texto interpretativo para el informe.
"""
from __future__ import annotations
import os
import tempfile
import warnings
from dataclasses import dataclass, field

import pandas as pd
import matplotlib
matplotlib.use("Agg")  # Backend sin GUI para generación de imágenes
import matplotlib.pyplot as plt
import seaborn as sns

warnings.filterwarnings("ignore")

# Estilo visual de los gráficos
sns.set_theme(style="whitegrid", palette="muted")
plt.rcParams.update({
    "figure.facecolor": "#FFFFFF",
    "axes.facecolor":   "#F9F9F9",
    "font.family":      "DejaVu Sans",
})

# Directorio temporal para guardar los gráficos del informe
_TMP_DIR = tempfile.mkdtemp(prefix="eda_charts_")


@dataclass
class EDAResult:
    """Contiene todos los resultados del análisis exploratorio."""
    shape: tuple[int, int]
    columns: list[str]
    dtypes: dict[str, str]
    null_counts: dict[str, int]
    null_pct: dict[str, float]
    quantitative_cols: list[str]
    qualitative_cols: list[str]

    # Estadísticas descriptivas
    descriptive_stats: pd.DataFrame | None = None

    # Tablas de frecuencia: {col: DataFrame(value, freq, pct)}
    frequency_tables: dict[str, pd.DataFrame] = field(default_factory=dict)

    # Tablas de contingencia: lista de (col_a, col_b, DataFrame)
    contingency_tables: list[tuple[str, str, pd.DataFrame]] = field(default_factory=list)

    # Rutas a imágenes generadas
    chart_paths: list[str] = field(default_factory=list)

    # Interpretación en texto
    interpretation: str = ""


def run_eda(
    df: pd.DataFrame,
    quantitative_cols: list[str],
    qualitative_cols: list[str],
) -> EDAResult:
    """
    Ejecuta el análisis exploratorio completo sobre el DataFrame.

    Args:
        df: Dataset cargado.
        quantitative_cols: Columnas numéricas indicadas por el usuario.
        qualitative_cols: Columnas categóricas indicadas por el usuario.

    Returns:
        EDAResult con todas las métricas y rutas de gráficos.
    """
    # --- Conversión robusta de columnas cuantitativas ---
    # Algunas columnas pueden venir como string aunque sean números
    # (ej. "280", "1.5"). Forzamos conversión silenciosa con errors='coerce'.
    df = df.copy()
    valid_quant_cols = []
    skipped_cols = []
    for col in quantitative_cols:
        if col not in df.columns:
            continue
        df[col] = pd.to_numeric(df[col], errors="coerce")
        pct_valid = df[col].notna().mean()
        if pct_valid < 0.05:
            # Menos del 5% de valores son numéricos → no es cuantitativa real
            skipped_cols.append(col)
        else:
            valid_quant_cols.append(col)

    quantitative_cols = valid_quant_cols

    result = EDAResult(
        shape=df.shape,
        columns=list(df.columns),
        dtypes={c: str(df[c].dtype) for c in df.columns},
        null_counts=df.isnull().sum().to_dict(),
        null_pct={c: round(df[c].isnull().mean() * 100, 2) for c in df.columns},
        quantitative_cols=quantitative_cols,
        qualitative_cols=qualitative_cols,
    )

    # Nota sobre columnas omitidas
    if skipped_cols:
        result.interpretation = (
            f"⚠️ Las siguientes columnas no pudieron procesarse como cuantitativas "
            f"porque contienen principalmente texto: {', '.join(skipped_cols)}. "
            f"Fueron omitidas del análisis numérico.\n\n"
        )

    # -- Estadísticas descriptivas
    quant_df = df[quantitative_cols] if quantitative_cols else pd.DataFrame()
    if not quant_df.empty:
        result.descriptive_stats = quant_df.describe().round(4)

    # -- Tablas de frecuencia (columnas cualitativas)
    for col in qualitative_cols:
        if col not in df.columns:
            continue
        freq = df[col].value_counts(dropna=False).reset_index()
        freq.columns = ["Valor", "Frecuencia"]
        freq["Porcentaje (%)"] = (freq["Frecuencia"] / len(df) * 100).round(2)
        result.frequency_tables[col] = freq.head(20)  # Top 20 para legibilidad

    # -- Tablas de contingencia (primeras 2 columnas cualitativas)
    if len(qualitative_cols) >= 2:
        for i in range(min(len(qualitative_cols) - 1, 2)):
            ca, cb = qualitative_cols[i], qualitative_cols[i + 1]
            if ca in df.columns and cb in df.columns:
                ct = pd.crosstab(df[ca], df[cb])
                result.contingency_tables.append((ca, cb, ct))

    # -- Gráficos
    result.chart_paths = _generate_charts(df, quantitative_cols, qualitative_cols)

    # -- Interpretación textual
    result.interpretation = result.interpretation + _build_interpretation(df, result)

    return result


# ---------------------------------------------------------------------------
# Generación de gráficos
# ---------------------------------------------------------------------------

def _save_fig(fig: plt.Figure, name: str) -> str:
    path = os.path.join(_TMP_DIR, f"{name}.png")
    fig.savefig(path, dpi=120, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return path


def _generate_charts(
    df: pd.DataFrame,
    quant_cols: list[str],
    qual_cols: list[str],
) -> list[str]:
    paths: list[str] = []

    # 1. Mapa de nulos
    paths.append(_chart_nulls(df))

    # 2. Histogramas + boxplots para cuantitativas
    for col in quant_cols:
        if col in df.columns:
            try:
                paths.append(_chart_quant(df, col))
            except Exception as e:
                warnings.warn(f"No se pudo graficar columna cuantitativa '{col}': {e}")

    # 3. Gráfico de barras para cualitativas
    for col in qual_cols:
        if col in df.columns:
            try:
                paths.append(_chart_qual(df, col))
            except Exception as e:
                warnings.warn(f"No se pudo graficar columna cualitativa '{col}': {e}")

    # 4. Mapa de correlación (si hay ≥ 2 cuantitativas)
    if len(quant_cols) >= 2:
        try:
            paths.append(_chart_correlation(df, quant_cols))
        except Exception as e:
            warnings.warn(f"No se pudo generar mapa de correlación: {e}")

    return [p for p in paths if p]


def _chart_nulls(df: pd.DataFrame) -> str:
    null_pct = (df.isnull().mean() * 100).sort_values(ascending=False)
    if null_pct.sum() == 0:
        # Sin nulos: gráfico informativo
        fig, ax = plt.subplots(figsize=(6, 2))
        ax.text(0.5, 0.5, "✓ Sin valores nulos", ha="center", va="center",
                fontsize=14, color="#27ae60", transform=ax.transAxes)
        ax.axis("off")
        ax.set_title("Campos Nulos / Vacíos", fontsize=12, fontweight="bold")
    else:
        fig, ax = plt.subplots(figsize=(max(8, len(df.columns) * 0.6), 4))
        colors = ["#e74c3c" if v > 20 else "#f39c12" if v > 5 else "#2ecc71" for v in null_pct]
        ax.bar(null_pct.index, null_pct.values, color=colors, edgecolor="white")
        ax.set_ylabel("% Nulos")
        ax.set_title("Porcentaje de Campos Nulos por Columna", fontsize=12, fontweight="bold")
        ax.tick_params(axis="x", rotation=45)
        for i, v in enumerate(null_pct.values):
            if v > 0:
                ax.text(i, v + 0.5, f"{v:.1f}%", ha="center", fontsize=8)
    fig.tight_layout()
    return _save_fig(fig, "nulls_overview")


def _chart_quant(df: pd.DataFrame, col: str) -> str:
    data = df[col].dropna()
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 4))

    # Histograma con KDE
    ax1.hist(data, bins="auto", color="#3498db", edgecolor="white", alpha=0.85)
    ax1.set_title(f"Distribución: {col}", fontsize=11, fontweight="bold")
    ax1.set_xlabel(col)
    ax1.set_ylabel("Frecuencia")

    # Añadir línea media y mediana
    ax1.axvline(data.mean(), color="#e74c3c", linestyle="--", linewidth=1.5, label=f"Media: {data.mean():.2f}")
    ax1.axvline(data.median(), color="#2ecc71", linestyle="--", linewidth=1.5, label=f"Mediana: {data.median():.2f}")
    ax1.legend(fontsize=8)

    # Boxplot
    bp = ax2.boxplot(data, patch_artist=True,
                     boxprops=dict(facecolor="#3498db", alpha=0.7),
                     medianprops=dict(color="#e74c3c", linewidth=2))
    ax2.set_title(f"Boxplot: {col}", fontsize=11, fontweight="bold")
    ax2.set_xticklabels([col])

    # Anotar cuartiles
    q1, q3 = data.quantile(0.25), data.quantile(0.75)
    ax2.text(1.25, data.median(), f"Med: {data.median():.2f}", va="center", fontsize=8, color="#e74c3c")
    ax2.text(1.25, q1, f"Q1: {q1:.2f}", va="center", fontsize=8, color="#555")
    ax2.text(1.25, q3, f"Q3: {q3:.2f}", va="center", fontsize=8, color="#555")

    fig.tight_layout()
    return _save_fig(fig, f"quant_{col.replace(' ', '_')[:20]}")


def _chart_qual(df: pd.DataFrame, col: str) -> str:
    counts = df[col].value_counts(dropna=False).head(15)
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5))

    # Barras horizontales
    colors = sns.color_palette("muted", len(counts))
    bars = ax1.barh(counts.index.astype(str), counts.values, color=colors, edgecolor="white")
    ax1.set_title(f"Frecuencia: {col}", fontsize=11, fontweight="bold")
    ax1.set_xlabel("Frecuencia")
    for bar, val in zip(bars, counts.values):
        ax1.text(val + 0.1, bar.get_y() + bar.get_height() / 2,
                 str(val), va="center", fontsize=8)

    # Gráfico de torta
    pct = counts.values / counts.values.sum() * 100
    wedges, _, autotexts = ax2.pie(
        counts.values,
        labels=[f"{l} ({p:.1f}%)" for l, p in zip(counts.index.astype(str), pct)],
        autopct="",
        colors=colors,
        startangle=140,
        wedgeprops=dict(edgecolor="white", linewidth=1.5),
    )
    ax2.set_title(f"Proporción: {col}", fontsize=11, fontweight="bold")

    fig.tight_layout()
    return _save_fig(fig, f"qual_{col.replace(' ', '_')[:20]}")


def _chart_correlation(df: pd.DataFrame, quant_cols: list[str]) -> str:
    corr = df[quant_cols].corr()
    n = len(quant_cols)
    fig, ax = plt.subplots(figsize=(max(6, n * 1.2), max(5, n * 1.0)))
    mask = pd.DataFrame(False, index=corr.index, columns=corr.columns)
    # Mostrar solo triángulo inferior
    for i in range(len(mask)):
        for j in range(i + 1, len(mask.columns)):
            mask.iloc[i, j] = True
    sns.heatmap(
        corr, mask=mask, annot=True, fmt=".2f", cmap="coolwarm",
        center=0, linewidths=0.5, ax=ax,
        cbar_kws={"shrink": 0.8},
        annot_kws={"size": 9},
    )
    ax.set_title("Matriz de Correlación (Variables Cuantitativas)", fontsize=12, fontweight="bold")
    fig.tight_layout()
    return _save_fig(fig, "correlation_matrix")


# ---------------------------------------------------------------------------
# Interpretación textual automática
# ---------------------------------------------------------------------------

def _build_interpretation(df: pd.DataFrame, r: EDAResult) -> str:
    lines: list[str] = []

    lines.append(f"El dataset contiene {r.shape[0]:,} registros y {r.shape[1]} columnas.")

    # Nulos
    total_nulls = sum(r.null_counts.values())
    if total_nulls == 0:
        lines.append("No se encontraron valores nulos ni vacíos en ninguna columna, lo que indica una buena calidad de los datos.")
    else:
        cols_con_nulos = [c for c, v in r.null_counts.items() if v > 0]
        lines.append(
            f"Se identificaron {total_nulls:,} valores nulos distribuidos en {len(cols_con_nulos)} columna(s): "
            f"{', '.join(cols_con_nulos[:5])}{'...' if len(cols_con_nulos) > 5 else ''}. "
            "Se recomienda analizar el origen de estos datos faltantes antes de modelar."
        )

    # Cuantitativas
    if r.descriptive_stats is not None:
        for col in r.quantitative_cols[:3]:  # Máximo 3 para no sobrecargar
            if col not in r.descriptive_stats.columns:
                continue
            stats = r.descriptive_stats[col]
            skew = df[col].dropna().skew()
            direction = "positiva (cola a la derecha)" if skew > 0.5 else "negativa (cola a la izquierda)" if skew < -0.5 else "aproximadamente simétrica"
            lines.append(
                f"La variable '{col}' presenta una media de {stats['mean']:.2f} y una desviación estándar de {stats['std']:.2f}. "
                f"Su distribución es {direction} (asimetría = {skew:.2f}). "
                f"Los valores oscilan entre {stats['min']:.2f} y {stats['max']:.2f}."
            )

    # Cualitativas
    for col, freq in list(r.frequency_tables.items())[:2]:
        top = freq.iloc[0]
        lines.append(
            f"La categoría más frecuente en '{col}' es '{top['Valor']}' "
            f"con {top['Frecuencia']:,} ocurrencias ({top['Porcentaje (%)']:.1f}% del total)."
        )

    # Correlación
    if len(r.quantitative_cols) >= 2:
        corr_df = df[r.quantitative_cols].corr()
        high_corr = [
            f"{c1}–{c2} ({corr_df.loc[c1, c2]:.2f})"
            for i, c1 in enumerate(r.quantitative_cols)
            for c2 in r.quantitative_cols[i + 1:]
            if abs(corr_df.loc[c1, c2]) > 0.7
        ]
        if high_corr:
            lines.append(
                f"Se detectaron correlaciones fuertes (|r| > 0.7) entre: {', '.join(high_corr[:3])}. "
                "Estas relaciones pueden ser relevantes para modelos predictivos."
            )
        else:
            lines.append("No se detectaron correlaciones lineales fuertes entre las variables cuantitativas analizadas.")

    return "\n\n".join(lines)