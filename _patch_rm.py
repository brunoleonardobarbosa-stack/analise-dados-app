"""Remove o bloco Fechados por TAG do app.py de teste."""

APP = r"C:\Users\BRUNOLEONARDO\Desktop\analise-dados-app-teste\app.py"

with open(APP, "r", encoding="utf-8") as fh:
    content = fh.read()

block = '''
            # ── Top TAGs com mais chamados fechados ──
            st.markdown("### Fechados por TAG (Top 20)")
            if "TAG" in closed_df.columns:
                tag_counts = (
                    closed_df["TAG"].astype("string").fillna("-")
                    .value_counts().head(20)
                    .rename_axis("TAG").reset_index(name="Quantidade")
                    .sort_values("Quantidade", ascending=True)
                )
                fig_tag = px.bar(
                    tag_counts, x="Quantidade", y="TAG", orientation="h", text_auto=True,
                    color_discrete_sequence=["#f59e0b"],
                )
                apply_dasa_plotly_theme(fig_tag)
                fig_tag.update_layout(yaxis_title="", xaxis_title="Quantidade")
                st.plotly_chart(fig_tag, use_container_width=True, key="closed_por_tag_chart")

'''

if block in content:
    content = content.replace(block, "\n")
    print("Bloco TAG removido!")
else:
    print("ERRO: bloco nao encontrado")

with open(APP, "w", encoding="utf-8") as fh:
    fh.write(content)
