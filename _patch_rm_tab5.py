"""Remove tab5 (Analise de Chamados Fechados) inteira do app.py de teste."""
import re

APP = r"C:\Users\BRUNOLEONARDO\Desktop\analise-dados-app-teste\app.py"

with open(APP, "r", encoding="utf-8") as fh:
    content = fh.read()

original_len = len(content)

# 1) Remover a funcao closed_calls_table inteira
#    Encontra "def closed_calls_table(" ate a proxima "def " no mesmo nivel (ou fim do arquivo)
pattern_func = r'\n# -{2,}.*?closed_calls_table.*?\ndef closed_calls_table\(df\):.*?(?=\ndef |\nclass )'
match_func = re.search(pattern_func, content, re.DOTALL)
if match_func:
    content = content[:match_func.start()] + "\n" + content[match_func.end():]
    print(f"1) Funcao closed_calls_table removida ({match_func.start()}-{match_func.end()})")
else:
    # tenta pattern mais simples
    pattern_func2 = r'\ndef closed_calls_table\(df\):.*?(?=\ndef |\nclass )'
    match_func2 = re.search(pattern_func2, content, re.DOTALL)
    if match_func2:
        content = content[:match_func2.start()] + "\n" + content[match_func2.end():]
        print(f"1) Funcao closed_calls_table removida (simples)")
    else:
        print("1) AVISO: funcao closed_calls_table nao encontrada")

# 2) Mudar st.tabs de 5 para 4 - remover tab5 e o label "Analise de Chamados Fechados"
#    Padrão: tab1, tab2, tab3, tab4, tab5 = st.tabs([...])
content = re.sub(
    r'tab1,\s*tab2,\s*tab3,\s*tab4,\s*tab5\s*=\s*st\.tabs\(',
    'tab1, tab2, tab3, tab4 = st.tabs(',
    content
)
# Remover o label da aba
content = re.sub(
    r'("Analise de Chamados Fechados")\s*,?\s*(?=\])',
    '',
    content
)
# Limpar virgula sobrando antes do ]
content = re.sub(r',\s*\]', ']', content)
print("2) st.tabs atualizado para 4 abas")

# 3) Remover bloco with tab5: inteiro
#    Encontra "with tab5:" e tudo indentado abaixo
lines = content.split('\n')
new_lines = []
inside_tab5 = False
tab5_indent = 0
i = 0
while i < len(lines):
    line = lines[i]
    stripped = line.lstrip()
    
    if stripped.startswith('with tab5:'):
        inside_tab5 = True
        tab5_indent = len(line) - len(stripped)
        i += 1
        continue
    
    if inside_tab5:
        if stripped == '' or stripped.startswith('#'):
            # linhas vazias ou comentarios dentro do bloco
            current_indent = len(line) - len(stripped) if stripped else tab5_indent + 1
            if stripped == '' or current_indent > tab5_indent:
                i += 1
                continue
            else:
                inside_tab5 = False
        elif len(line) - len(stripped) > tab5_indent:
            i += 1
            continue
        else:
            inside_tab5 = False
    
    if not inside_tab5:
        new_lines.append(line)
    i += 1

content = '\n'.join(new_lines)
print("3) Bloco with tab5 removido")

with open(APP, "w", encoding="utf-8") as fh:
    fh.write(content)

new_len = len(content)
print(f"\nTamanho: {original_len} -> {new_len} ({original_len - new_len} chars removidos)")
print("CONCLUIDO!")
