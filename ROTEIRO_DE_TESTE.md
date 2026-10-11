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
| `python seed.py --volume 300` | quantidade de matérias extras para os gráficos (padrão 120; 0 = nenhuma) |

O seed nunca mexe no que **você** cadastrou. Se algum item da verificação aparecer como
`FALHA`, copie a saída do terminal e me envie.

## 1. Cabeçalho e navegação

- [ ] A data por extenso e o "Sistema redatorial ativo" aparecem no topo.
- [ ] Os itens Notícias, Categorias, Autores e Gráficos trocam de tela; o ativo fica vermelho com sublinhado.
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

## 7. Gráficos & Análise

Rode antes `python seed.py` (ele cria 120 matérias extras espalhadas pelos últimos 120 dias, com
picos às terças e quartas, para os gráficos terem o que mostrar).

- [ ] Abrir a aba **Gráficos**: 4 indicadores, gráfico de barras "Notícias por Categoria", "Evolução no Período", "Produtividade por Autor", "Volume ao Longo da Semana", "Pipeline Redatorial", "Leitura dos dados" e "Meta do período".
- [ ] As barras ficam ordenadas da editoria com mais matérias para a com menos, cada uma com sua cor, número e percentual; as editorias sem matérias não aparecem.
- [ ] **Período**: Últimos 7 / 30 / 90 dias, 12 meses, Este ano e Todo o período mudam todos os números e gráficos. Em "Todo o período" a comparação some ("sem comparação") e a evolução passa a ser por mês.
- [ ] **Personalizado…**: aparecem os campos de data; datas inválidas (`32/13/2024`) ou início depois do fim avisam; datas válidas aplicam.
- [ ] **Editoria**: escolher uma editoria isola o gráfico e todos os números nela. **Jornalista** faz o mesmo por autor.
- [ ] **Estado da matéria**: "Publicadas" (padrão), "Todos os estados", Rascunhos, Em pauta e Em revisão; o rótulo do primeiro indicador muda para "Total de matérias" quando não é "Publicadas".
- [ ] Combinar filtros que não têm resultado (ex.: Joana Freitas + qualquer editoria) mostra o aviso de recorte vazio, sem erro.
- [ ] **Limpar filtros** volta ao padrão (30 dias, publicadas, tudo).
- [ ] Indicador "Total publicado" mostra a variação contra o período anterior (↑ verde / ↓ vermelho); "Editorias em operação" mostra X de Y editorias ativas; a média de leituras também compara com o período anterior.
- [ ] "Produtividade por Autor" mostra os 5 primeiros com cargo e score; "Ver tabela completa" abre todos, com leituras e média.
- [ ] "Volume ao Longo da Semana" destaca em vermelho e negrito os dias de pico (terça e quarta no seed) e a observação crítica cita esses dias.
- [ ] "Pipeline Redatorial" mostra a última publicação e a fila de revisão; criar uma matéria em outra aba e voltar atualiza os números. A tela também se atualiza sozinha a cada minuto.
- [ ] **Meta do período**: editar o número e apertar Enter muda a barra e o texto; fechar e reabrir o programa mantém a meta e o último período/estado escolhidos (`config/graficos.json`).
- [ ] **Exportar relatório PDF** gera um arquivo de 3 páginas (indicadores e autores, distribuição, semana e evolução) que abre no leitor de PDF; **Exportar CSV** abre no Excel com acentos corretos.
- [ ] Redimensionar a janela: os gráficos acompanham a largura dos cartões e nada fica cortado.
- [ ] Com o MySQL parado, a tela mostra o erro sem fechar o programa.

## 8. Notificações (sino do cabeçalho)

Depois de rodar `python seed.py`, o painel já tem 8 despachos de exemplo (1 urgente, de várias idades).

- [ ] O envelope ✉ no cabeçalho mostra um **selo vermelho** com o número de não lidas ("99+" se passar de 99); o selo some quando não há nenhuma.
- [ ] Clicar no envelope abre o painel pelo lado direito; ✕, Esc ou clicar de novo no envelope fecham.
- [ ] Abas **Todas / Não lidas / Urgente** com contagens corretas; "Marcar lidas" zera as não lidas e o selo.
- [ ] Cartões: tipo do despacho, etiqueta (a de furo aparece em vermelho), tempo ("HÁ 12 MIN", "HÁ 3 HORAS", "ONTEM ÀS 22:00", "22 MAI", com o ano se for de outro ano), título, texto e rodapé. Não lidas têm ponto vermelho; a urgente fica destacada.
- [ ] Clicar num cartão marca como lido e **leva ao assunto**: matéria → leitura; editoria → Categorias; autor → Autores; aviso de segurança → Perfil.
- [ ] Criar, publicar, enviar à revisão ou excluir uma matéria, e criar/editar/excluir editorias e autores, **gera novos despachos** (o selo sobe sozinho). Editar uma matéria sem mudar o estado dela não gera aviso.
- [ ] Publicar uma matéria com a etiqueta `#Urgente` ou `#Furo` gera um "Furo de reportagem" urgente.
- [ ] Com **Alertas sonoros** ligado no Perfil, um furo novo toca o sinal do sistema (uma vez por furo; não toca ao abrir o programa por causa de despachos antigos). Desligado, fica em silêncio.
- [ ] "Ver histórico completo…" abre a lista com filtro e páginas; duplo clique abre o assunto.
- [ ] "Configurar alertas do plantão" abre o Perfil.
- [ ] Cada usuário tem o próprio "lido": entrar com outra conta mostra tudo como não lido para ela.

## 9. Perfil (clicar no nome do usuário no cabeçalho)

- [ ] O cabeçalho da tela mostra o prontuário (`NM-0001/ano`) e se a verificação em duas etapas está ativa.
- [ ] **Crachá**: foto (ou a inicial), nome, cargo, matrícula, registro, conselho, mesa, nota biográfica, último fechamento e total de matérias do acervo.
- [ ] **Trocar foto** e **Remover** funcionam (o arquivo antigo some de `midia/autores`); arquivo que não é imagem é recusado.
- [ ] **Módulo 01**: editar os dados e "Salvar dados biográficos" atualiza o crachá, o nome no cabeçalho e o "Alterado por … em …". Nome vazio é recusado. O e-mail aparece bloqueado (🔒).
- [ ] **Módulo 02**: as regras da senha nova mudam de ○ para ✓ enquanto você digita (12+ caracteres, símbolos, letras e números, diferente da atual, confirmação igual).
- [ ] Trocar a senha: senha atual errada, nova fraca e confirmação diferente são recusadas com a mensagem certa; com tudo certo, os campos limpam, o login passa a aceitar só a senha nova e aparece o despacho "Senha Atualizada" (só para você).
- [ ] Conta que entra só pelo Google: os campos de senha ficam desabilitados com uma explicação.
- [ ] **Ativar 2FA** abre o assistente (código por e-mail); **Desativar 2FA** pede confirmação; ambos geram despacho de segurança e atualizam o selo do cabeçalho.
- [ ] **Módulo 03** — preferências por usuário, salvas em "Preservar preferências do operador":
  - [ ] *Alertas sonoros*: veja o item do painel de notificações.
  - [ ] *Despachos por e-mail*: com o envio de e-mail configurado, um furo urgente chega por e-mail; sem configuração aparece o aviso em vermelho.
  - [ ] *Revisão automática*: no editor, o texto ganha realce amarelo em espaços duplos, palavras repetidas, falta de espaço, frases iniciadas em minúscula e frases longas; o contador mostra "REVISÃO: N APONTAMENTO(S)" e, ao clicar nele, lista os problemas.
  - [ ] *Polegadas de coluna*: no editor, o contador troca "caracteres" por "pol. de coluna" e a ficha de rotativa mostra as duas medidas.
- [ ] Fechar e reabrir o programa mantém as preferências.
- [ ] **Sair do sistema** (cartão lateral) volta ao login.

## 10. Limpeza

- [ ] `python seed.py --limpar` remove as matérias, autores, editorias e **imagens** do seed; o que você criou continua lá.
- [ ] A pasta `midia/` não fica com arquivos soltos (rode `python seed.py --verificar` antes de limpar: ele avisa se houver imagens órfãs).
