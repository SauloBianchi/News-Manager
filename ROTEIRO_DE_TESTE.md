# Roteiro de teste com o seed

Este roteiro serve para conferir **na janela real** o que foi testado só em simulação.
Marque cada item e anote o que estranhar (print ajuda muito).

## 0. Preparação

```powershell
pip install -r requirements.txt          # inclui o Pillow (imagens)
python seed.py                           # cria os dados de teste e roda as verificações
python main.py                           # abre o sistema e entra com seu usuário
```

Outras opções do seed:

| Comando | O que faz |
|---|---|
| `python seed.py --verificar` | só confere, sem alterar nada |
| `python seed.py --autosave` | cria também um auto-salvamento de exemplo (seção 5, item de auto-salvamento) |
| `python seed.py --recriar` | apaga o que o seed criou e cria tudo de novo |
| `python seed.py --limpar` | remove só os dados do seed (e as imagens deles) |
| `python seed.py --sem-imagens` | popula sem capas/fotos |

O seed nunca mexe no que **você** cadastrou. Se algum item da verificação aparecer como
`FALHA`, copie a saída do terminal e me envie.

## 1. Cabeçalho e navegação

- [ ] A data por extenso e o "Sistema redatorial ativo" aparecem no topo.
- [ ] Os itens Notícias, Categorias, Autores, Gráficos e Segurança trocam de tela; o ativo fica vermelho com sublinhado.
- [ ] Parar o MySQL com o sistema aberto muda o status para "Banco de dados desconectado" em até 30 s.
- [ ] **Sair** pergunta, volta ao login, e ao entrar de novo **as imagens continuam aparecendo** (testa a correção do cache).
- [ ] Redimensionar a janela até o mínimo não corta os botões do cabeçalho.

## 2. Categorias

- [ ] Cartões do topo: "editorias ativas", "caderno mais ativo" (Tecnologia & Ciência ou Economia) e a média por caderno.
- [ ] A tabela mostra 10+ editorias com etiqueta colorida, barra de volume, última edição ("Hoje", "Ontem", "Seg 12 Set") e status.
- [ ] **Esportes & Lazer** aparece como "Em revisão".
- [ ] Buscar `inteligência` filtra por descrição; buscar `#CAT-` mostra o código.
- [ ] Criar uma editoria (nome, resumo, cor, status) → aparece na tabela.
- [ ] Criar com o mesmo nome em minúsculas → aviso de duplicada.
- [ ] Editar uma editoria muda cor e status.
- [ ] Excluir **Economia & Negócios** → bloqueado, informando quantas matérias tem.
- [ ] Excluir **Saúde & Bem-estar** (sem matérias) → exclui.
- [ ] "Relatório geral (CSV)" salva um arquivo que abre no Excel com acentos corretos.

## 3. Autores

- [ ] 10 cartões em 2 páginas (6 + 4); a paginação funciona.
- [ ] Filtros "Todos / Repórteres / Colunistas / Editores setoriais / Correspondentes" mostram as contagens certas.
- [ ] Autores com foto mostram a foto com a inicial num selo; **Roberto Fontes, Mariana Alencar, Redação NewsManager e Joana Freitas** mostram só a inicial.
- [ ] **Sofia Ramalho** mostra "Status: Em pauta externa".
- [ ] A bio longa da **Teresa Castelo** é cortada com "…" no cartão.
- [ ] Buscar `MTB 0031849` encontra a Teresa; buscar `Londres` encontra o Gabriel.
- [ ] "Ver matérias" abre a lista de matérias do autor.
- [ ] Criar autor com foto; trocar a foto; remover a foto (o arquivo antigo some de `midia/autores`).
- [ ] E-mail repetido e e-mail inválido são recusados.
- [ ] Excluir a **Teresa** → bloqueado; excluir a **Joana Freitas** → exclui.

## 4. Notícias — feed e editor rápido

- [ ] Painel "Cadência da tiragem": gráfico por seção, "plantão do telégrafo" com 2 matérias em revisão, total em circulação.
- [ ] Feed em 3 páginas de 6 cartões; capas aparecem nos cartões com foto, faixa colorida nos demais.
- [ ] Os **dois cartões de destaque** (reforma tributária e editorial) aparecem escuros com selo "Destaque".
- [ ] Filtros por seção e por estado (Rascunho, Em pauta, Revisão, Publicado) e ordenação (Mais lidas deve começar pelo editorial, 14.8k).
- [ ] Buscar `100%` encontra **só** a matéria de caracteres especiais (não pode listar tudo).
- [ ] Buscar `_sublinhados_`, `IBS` (etiqueta) e `Teresa` (autor) funcionam.
- [ ] Datas dos cartões: matéria de mais de um ano mostra o ano; a embargada mostra o horário futuro.
- [ ] **Editor rápido**: criar uma matéria curta como rascunho; editar; atualizar; excluir.
- [ ] "Abrir no editor completo →" leva o que está digitado para o editor completo.

## 5. Editor completo (Nova Matéria)

- [ ] "+ Nova matéria" no cabeçalho abre a tela; a trilha mostra "NOVA MATÉRIA".
- [ ] Digitar título mostra o contador "x / 120"; passar de 120 deixa o contador vermelho.
- [ ] Selecionar uma palavra e clicar **B**, **I**, **U** (ou Ctrl+B/I/U) envolve com marcadores; clicar de novo remove.
- [ ] **H2**, **H3**, citação, lista e lista numerada funcionam na linha do cursor e em várias linhas selecionadas.
- [ ] Link: `https://exemplo.com` entra; `javascript:alert(1)` é recusado.
- [ ] **IMG** insere uma imagem no texto; **—** insere um filete.
- [ ] O texto formatado é realçado (negrito em negrito, intertítulo grande e vermelho, marcadores esmaecidos).
- [ ] Contadores: palavras, caracteres, colunas; a ficha mostra Flesch, tempo de leitura e embargo.
- [ ] Marcar data no futuro + estado Publicado → "Bloqueio de galé: Ativo até …".
- [ ] Etiquetas: adicionar com Enter, remover com ×, limite de 8.
- [ ] Capa com legenda e crédito; manchete só vale ao publicar.
- [ ] **Chip** muda de "● alterações não salvas" para "✓ tudo salvo" ao salvar.
- [ ] **Salvar rascunho** mantém na tela; **Publicar matéria** abre a leitura.
- [ ] Editar a matéria do seed "Reforma Tributária…" → tudo carrega (capa, imagem no texto, etiquetas, data e hora).
- [ ] Trocar a capa e salvar → a capa antiga some de `midia/noticias`.
- [ ] Despublicar (Salvar rascunho numa publicada) pede confirmação.
- [ ] Ctrl+Z logo depois de abrir **não** apaga o texto carregado.
- [ ] **Auto-salvamento:** (com `--autosave`) "+ Nova matéria" oferece recuperar o rascunho de exemplo. Digitar algo, esperar ~20 s: o horário do último auto-salvamento aparece e surge `rascunhos/autosave_*.json`; fechar o programa à força e reabrir oferece recuperar.
- [ ] Sair com alterações não salvas (trocar de aba, Cancelar) pergunta antes.
- [ ] Cancelar uma matéria nova apaga a capa/imagem que você tinha carregado sem salvar.

## 6. Leitura da matéria

- [ ] "Ler" num cartão abre a página inteira; o contador de leituras sobe 1 (só para publicadas; rascunho/revisão não contam).
- [ ] Título, linha fina, faixa de autoria com foto, capa com legenda e crédito.
- [ ] "Nesta edição" lista os intertítulos; clicar rola até a seção (testar na matéria **Dossiê**, que é longa).
- [ ] Texto: capitular, "§ 1." nos intertítulos, citação com autoria, listas, filete, imagem com legenda, link clicável.
- [ ] Na matéria de **caracteres especiais**: o `<script>` aparece como texto; o link `javascript:` não é clicável.
- [ ] Palavras-chave clicáveis filtram o feed; "Todas as matérias deste repórter" filtra pelo autor.
- [ ] "Contato via despacho" copia o e-mail (a Mariana Alencar avisa que não tem).
- [ ] "Leituras suplementares" mostra até 3 da mesma editoria (sem rascunhos); "Ver todo o acervo" filtra o feed pela editoria.
- [ ] Copiar referência, Exportar HTML (abrir no navegador e imprimir/salvar em PDF), Editar e Excluir.
- [ ] Redimensionar a janela com a página aberta não deixa o texto cortado nem com espaço sobrando.

## 7. Gráficos e Segurança

- [ ] O gráfico "Notícias por Categoria" reflete os dados do seed e atualiza depois de criar/excluir matérias.
- [ ] A aba Segurança abre e o botão de 2FA continua funcionando.

## 8. Limpeza

- [ ] `python seed.py --limpar` remove as matérias, autores, editorias e **imagens** do seed; o que você criou continua lá.
- [ ] A pasta `midia/` não fica com arquivos soltos (rode `python seed.py --verificar` antes de limpar: ele avisa se houver imagens órfãs).
