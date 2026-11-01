"""
seed.py
Dados de teste do NewsManager + verificação automática das funcionalidades.

Uso (na pasta do projeto, com o MySQL rodando):

    python seed.py                 popula o banco e roda as verificações
    python seed.py --verificar     só roda as verificações (não altera nada)
    python seed.py --limpar        remove apenas os dados criados por este script
    python seed.py --recriar       limpar + popular + verificar
    python seed.py --autosave      também cria um auto-salvamento de exemplo, para
                                   testar a recuperação no editor ("+ Nova matéria")
    python seed.py --sem-imagens   não gera capas nem fotos (não precisa de Pillow)
    python seed.py --volume 300    quantidade de matérias extras para os gráficos (padrão 120;
                                   0 = não cria). Elas ficam espalhadas pelos últimos 120 dias,
                                   com picos às terças e quartas, para as estatísticas fazerem sentido.

Opções de conexão (iguais às do main.py por padrão):
    --host localhost --usuario root --senha "" --banco newsmanager

O script usa as mesmas classes do sistema (CategoriaService, AutorService e
NoticiaService), então popular o banco já exercita as regras de validação, a
importação de imagens e a migração automática de colunas. Pode ser rodado
várias vezes: o que já existe não é duplicado.

O que é criado: 9 editorias, 10 autores (com e sem foto), 18 matérias em todos
os estados (rascunho, em pauta, revisão, publicada, manchete, embargada), com
capa, imagens no texto, etiquetas, links, listas, citações, caracteres
especiais e uma matéria longa. O roteiro do que conferir na tela está em
ROTEIRO_DE_TESTE.md.
"""

import argparse
import json
import math
import random
import re
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
sys.path.insert(0, str(RAIZ))

from app import clipping as clipping_mod  # noqa: E402
from app import tempo as tempo_mod  # noqa: E402
from app.cadastros import AutorService, CategoriaService  # noqa: E402
from app.database import DatabaseManager, ErroBanco  # noqa: E402
from app.estatisticas import EstatisticasService, FiltroEstatisticas  # noqa: E402
from app.logger import Logger  # noqa: E402
from app.midia import ErroMidia, disponivel as pillow_disponivel  # noqa: E402
from app.midia import midia as gerenciador_midia  # noqa: E402
from app.noticias import NoticiaService  # noqa: E402
from app.notificacoes import NotificacaoService, silenciar, tempo_relativo  # noqa: E402
from app.perfil import PerfilService, avaliar_senha  # noqa: E402
from app.texto_rico import (  # noqa: E402
    blocos,
    caminhos_de_imagens,
    classificar_flesch,
    colunas_estimadas,
    contar_palavras,
    indice_flesch,
    intertitulos,
    pagina_html,
    texto_simples,
)

DOMINIO_EMAIL = "seed.newsmanager.local"
CATEGORIAS_DO_SCHEMA = {"Política", "Esportes", "Tecnologia", "Economia"}   # vêm do schema.sql: nunca removidas
MARCA_AUTOSAVE = "Rascunho recuperável (exemplo do seed)"
ATOR_SEED = "seed.py"          # marca as notificações criadas por este script (para o --limpar)
PREFIXO_VOLUME = "Volume #"

# ---------------------------------------------------------------------------
# Dados
# ---------------------------------------------------------------------------
CATEGORIAS = [
    # nome, descrição, cor, status
    ("Política", "Cobertura de plenário, ministérios, políticas públicas e relações institucionais de governo.", "rubro", "ativa"),
    ("Economia & Negócios", "Indicadores macroeconômicos, mercados financeiros, balanços corporativos e tributação.", "azul", "ativa"),
    ("Tecnologia & Ciência", "Avanços computacionais, inteligência artificial, espaço e pesquisas acadêmicas de vanguarda.", "sepia", "ativa"),
    ("Cultura & Artes", "Crítica literária, artes plásticas, estreias teatrais, ensaios estéticos e cinema autoral.", "carvao", "ativa"),
    ("Mundo & Diplomacia", "Relações bilaterais, tratados internacionais, conflitos geopolíticos e despachos de correspondentes.", "azul", "ativa"),
    ("Opinião & Artigos", "Editoriais da casa, crônicas semanais, cartas dos leitores e artigos de articulistas convidados.", "rubro", "ativa"),
    ("Esportes & Lazer", "Campeonatos nacionais, olimpismo, automobilismo e análise tática esportiva.", "carvao", "em_revisao"),
    ("Meio Ambiente & Clima", "Transição energética, eventos climáticos extremos, biomas e conferências ambientais globais.", "sepia", "ativa"),
    ("Saúde & Bem-estar", "Saúde pública, pesquisas clínicas, prevenção e qualidade de vida.", "rubro", "ativa"),
]

BIO_LONGA = (
    "Especialista em trâmites constitucionais e cobertura do Supremo Tribunal Federal, com mais de dezoito "
    "anos de imprensa. Passou pelas redações de Brasília e São Paulo, coordenou a cobertura de três eleições "
    "gerais e é autora de dois livros-reportagem sobre o processo legislativo brasileiro. Dá aulas de "
    "jornalismo político e acompanha de perto as comissões do Congresso Nacional."
)

AUTORES = [
    # nome, função, cargo, registro, status, foto?, e-mail?, bio, cor do avatar
    ("Teresa Castelo", "editor_setorial", "Editora de Política • Brasília", "MTB 0031849/DF", "ativo", True, True, BIO_LONGA, (139, 30, 30)),
    ("Henrique Alcântara", "colunista", "Analista de Mercado • SP", "MTB 0029144/SP", "ativo", True, True,
     "Cobertura diária do Ibovespa, taxa de juros e relatórios analíticos de risco macroeconômico global.", (79, 94, 129)),
    ("Beatriz Lins", "reporter", "Repórter de Ciência • Futuro", "MTB 0041289/RJ", "ativo", True, True,
     "Focada em transição energética, inteligência artificial e pesquisas clínicas em universidades ibero-americanas.", (90, 68, 38)),
    ("Gabriel Esteves", "correspondente", "Correspondente • Londres / Bruxelas", "MTB 0019842/SP", "ativo", True, True,
     "Crônicas diplomáticas sobre a União Europeia, acordos multilaterais e dinâmicas políticas do Atlântico Norte.", (28, 28, 23)),
    ("Sofia Ramalho", "reporter", "Repórter Especial de Investigação", "MTB 0055201/MG", "em_pauta_externa", True, True,
     "Jornalismo de dados, cruzamento de registros orçamentários públicos e desdobramentos de crimes financeiros.", (139, 30, 30)),
    ("Roberto Fontes", "colunista", "Colunista de Análise Social • Cultura", "MTB 0012003/RJ", "ativo", False, True,
     "Críticas literárias, ensaios sobre urbanismo contemporâneo e crônicas dominicais de comportamento.", (79, 94, 129)),
    ("Mariana Alencar", "reporter", "Repórter de Cultura", None, "ativo", False, False,
     "Autora sem e-mail e sem registro cadastrados (testa os campos vazios).", (90, 68, 38)),
    ("Carlos Eduardo Silva", "correspondente", "Correspondente Sênior • Economia", "MTB 0027711/DF", "ativo", True, True,
     "Jornalista especializado em macroeconomia, finanças públicas e comércio exterior.", (79, 94, 129)),
    ("Redação NewsManager", "editor_setorial", "Conselho Editorial", None, "ativo", False, True, None, (28, 28, 23)),
    ("Joana Freitas", "reporter", "Repórter de Saúde", "MTB 0060123/RS", "ativo", False, True,
     "Autora sem nenhuma matéria: serve para testar a exclusão de um autor livre.", (139, 30, 30)),
]

PARAGRAFOS = [
    "A decisão chega depois de meses de negociação entre o governo, a oposição e representantes dos setores diretamente afetados, que defendiam prazos de adaptação mais longos.",
    "Segundo fontes ouvidas pela reportagem, o texto final preservou os pontos centrais da proposta original, mas incorporou emendas que ampliam a transparência na prestação de contas.",
    "Especialistas consultados avaliam que os efeitos práticos só poderão ser medidos ao longo dos próximos trimestres, quando os primeiros relatórios de acompanhamento forem divulgados.",
    "Para os moradores das regiões mais afetadas, a expectativa é de que as mudanças se traduzam em serviços melhores, e não apenas em novos formulários e procedimentos.",
    "O debate, no entanto, está longe de terminar: entidades de classe já anunciaram que vão pedir esclarecimentos e acompanhar de perto a regulamentação complementar.",
    "Em nota, o órgão responsável afirmou que o cronograma será cumprido e que haverá canais específicos para dúvidas de cidadãos e empresas durante todo o período de transição.",
    "Historicamente, medidas desse tipo levam alguns anos para se consolidar, e os resultados costumam variar bastante conforme o porte e a localização de cada instituição.",
    "A reportagem procurou os envolvidos para comentar os números apresentados e atualizará este texto assim que houver novas informações oficiais.",
]


def corpo_curto(tema: str, n: int = 3, citacao: str = None, lista: list = None) -> str:
    """Corpo de matéria simples: um parágrafo de abertura com o tema e n parágrafos de apoio."""
    partes = [f"{tema}"]
    partes += [PARAGRAFOS[(i * 3 + len(tema)) % len(PARAGRAFOS)] for i in range(n)]
    if citacao:
        partes += [f"> {citacao}", "> — Fonte ouvida pela reportagem"]
    if lista:
        partes += [f"- {item}" for item in lista]
    return "\n".join(partes)


def corpo_dossie() -> str:
    """Matéria longa (cerca de 1.500 palavras, 6 capítulos) para testar rolagem, sumário e estatísticas."""
    capitulos = [
        "A chegada dos computadores às mesas de redação",
        "A internet e o fim do fechamento único",
        "Redes sociais e a disputa pela atenção",
        "Dados, algoritmos e novas rotinas de apuração",
        "O desafio da confiança e da checagem",
        "O que vem pela frente",
    ]
    partes = []
    for numero, titulo in enumerate(capitulos, start=1):
        partes.append(f"## Capítulo {numero} — {titulo}")
        for i in range(6):
            partes.append(PARAGRAFOS[(numero * 2 + i) % len(PARAGRAFOS)])
        if numero == 2:
            partes.append("> A velocidade mudou, mas a responsabilidade de apurar continua sendo a mesma de sempre.")
            partes.append("> — Editora-chefe de uma redação regional")
        if numero == 3:
            partes.append("![Linha do tempo da digitalização](__IMAGEM_INLINE__)")
        if numero == 4:
            partes += ["- Coleta automática de documentos públicos", "- Cruzamento de bases de dados", "- Visualização de dados para o leitor"]
        if numero == 5:
            partes += ["1. Verificar a origem da informação", "2. Confrontar com ao menos uma segunda fonte", "3. Registrar a correção quando houver erro"]
    return "\n".join(partes)


CORPO_MANCHETE = """## A Transição das Alíquotas e o Veto aos Benefícios Regionais
A promulgação do novo ordenamento fiscal abre um capítulo de **reconfigurações sem precedentes** nos canais de suprimento do comércio nacional. Enquanto as lideranças da pasta econômica afirmam a *imperatividade da simplificação* dos cinco tributos anteriores em um único imposto sobre valor agregado, os balanços corporativos já sentem os reflexos imediatos nos cálculos de créditos acumulados.
> Não se trata apenas de uma redução burocrática teórica, mas da reconstrução completa de margens operacionais fixadas há mais de quatro décadas.
> — Dra. Helena Monteneiro, diretora do Instituto de Estudos Fazendários
## Perspectiva dos Pequenos Negócios
A manutenção do __Simples Nacional__ garante, em tese, a neutralidade do novo regime para as pequenas empresas. Na prática, porém, a cadeia produtiva depende do repasse de créditos entre fornecedores e compradores, e é nesse ponto que os especialistas veem o maior risco.
- Crédito integral para quem compra de fornecedores optantes
- Alíquota reduzida para os itens da cesta básica nacional
- Devolução de parte do imposto para famílias de baixa renda
O calendário de implantação foi desenhado em etapas:
1. Aprovação final no Senado Federal
2. Regulamentação por lei complementar
3. Período de transição de sete anos
---
![Mercado público em dia de feira](__IMAGEM_INLINE__)
### Para saber mais
O texto completo da proposta está disponível no [portal da Receita Federal](https://www.gov.br/receitafederal). A reportagem seguirá acompanhando a votação.
## Projeções Macroeconômicas para a Próxima Década
Modelagens econométricas apontam que a eficiência sistêmica gerada pelo fim do efeito cumulativo e pela eliminação dos custos jurídicos de contencioso pode adicionar até 12% ao produto interno bruto potencial ao longo de quinze anos. O maior entrave segue sendo a volatilidade da alíquota de referência, estimada inicialmente em 26,5%, uma das mais elevadas entre as economias congêneres da OCDE.
Para os diretores executivos do varejo, o cronograma exige audácia e contenção. O processo de precificação dos estoques durante os anos híbridos dependerá de investimentos substanciais em inteligência analítica de dados e conformidade fiscal."""

CORPO_ESPECIAIS = """Este texto testa **caracteres especiais** e a busca: 100% de aprovação, uma conta como 5 * 3 * 2 e nomes_com_sublinhado.
Aspas “curvas”, aspas 'simples', travessão — e acentuação completa: ação, coração, órgão, ônibus, pingüim, à, ç, ã, õ.
Uma tentativa de injeção que deve aparecer como texto puro: <script>alert("xss")</script> e <b>não é negrito</b>.
Link perigoso que NÃO deve virar link: [clique aqui](javascript:alert(1)) — e um link seguro: [site de exemplo](https://exemplo.com)."""

# ---------------------------------------------------------------------------
# Matérias: (chave de capa, título, subtítulo, categoria, autor, status, destaque,
#            etiquetas, quando, leituras, corpo)
# `quando` = (dias atrás, horas atrás) ou ("fixo", dias atrás, "HH:MM"); dias negativos = futuro.
# ---------------------------------------------------------------------------
def materias():
    return [
        dict(titulo="Reforma Tributária e os Novos Desafios Estruturais para o Varejo Nacional",
             subtitulo="A unificação dos tributos federal e subnacionais obriga redes varejistas e médios distribuidores a rever fluxos de crédito, contratos de fornecimento e a precificação final ao consumidor.",
             categoria="Economia & Negócios", autor="Carlos Eduardo Silva", status="publicado", destaque=True,
             etiquetas="#ReformaTributária, #Varejo, #IBS, #CBS", quando=("fixo", 0, "08:30"), leituras=8400,
             capa=True, legenda="Sala de redação e arquivos de uma gráfica antiga, onde as pautas tributárias eram compostas.",
             credito="Acervo histórico / Agência Gazeta", corpo=CORPO_MANCHETE, inline=True),
        dict(titulo="Avanços em Inteligência Artificial Redefinem a Produção de Notícias",
             subtitulo="Modelos generativos e redações automatizadas abrem novos debates éticos sobre curadoria jornalística, verificação factográfica e direitos autorais.",
             categoria="Tecnologia & Ciência", autor="Beatriz Lins", status="publicado", destaque=False,
             etiquetas="#IA, #Jornalismo, #Ética", quando=(0, 2), leituras=3100, capa=True,
             legenda="Rotativa moderna em operação.", credito="Agência Gazeta",
             corpo=corpo_curto("Redações de todo o país testam ferramentas de inteligência artificial para apoiar a apuração e a edição.", 4,
                               "A tecnologia ajuda, mas a decisão editorial continua sendo humana.", ["Transcrição de entrevistas", "Sugestão de títulos", "Checagem de dados"])),
        dict(titulo="Bienal Internacional do Livro Celebra Centenário de Autores Modernistas",
             subtitulo="Com curadoria especial e homenagens a poetas clássicos, a abertura reúne recorde de público e debates essenciais sobre a sobrevida do impresso.",
             categoria="Cultura & Artes", autor="Mariana Alencar", status="publicado", destaque=False,
             etiquetas="#Livros, #Bienal, #Modernismo", quando=(1, 0), leituras=5900, capa=True,
             legenda="Visitantes percorrem os corredores da feira.", credito="Divulgação",
             corpo=corpo_curto("A abertura da Bienal reuniu escritores, editores e leitores de todas as gerações.", 4)),
        dict(titulo="Cúpula Global do Clima Estabelece Metas Vinculantes para 2030",
             subtitulo="Líderes de mais de cento e vinte países assinam compromisso de investimento conjunto em energia renovável, transição ecológica e metas fiscais conjuntas.",
             categoria="Meio Ambiente & Clima", autor="Gabriel Esteves", status="publicado", destaque=False,
             etiquetas="#Clima, #COP, #EnergiaLimpa", quando=(2, 0), leituras=11200, capa=True,
             legenda="Delegações no plenário da cúpula.", credito="Agência Internacional",
             corpo=corpo_curto("As metas foram aprovadas por consenso após uma madrugada de negociações.", 3,
                               "É a primeira vez que os compromissos têm prazo e mecanismo de cobrança.")),
        dict(titulo="Novo Polo Científico e Tecnológico é Inaugurado no Parque Tecnológico",
             subtitulo="Iniciativa público-privada atrai mais de R$ 400 milhões em pesquisa aplicada nas áreas de biotecnologia e matrizes de energias limpas.",
             categoria="Tecnologia & Ciência", autor="Beatriz Lins", status="publicado", destaque=False,
             etiquetas="#Pesquisa, #Inovação", quando=(3, 0), leituras=4700, capa=False,
             corpo=corpo_curto("O novo polo reúne laboratórios, startups e centros de pesquisa em um mesmo campus.", 3)),
        dict(titulo="Editorial: Os Desafios do Jornalismo Investigativo na Era dos Algoritmos",
             subtitulo="A preservação da checagem rigorosa de fontes e da independência editorial frente à velocidade vertiginosa das redes e à desinformação monetizada.",
             categoria="Opinião & Artigos", autor="Redação NewsManager", status="publicado", destaque=True,
             etiquetas="#Editorial, #Jornalismo", quando=(3, 4), leituras=14800, capa=False,
             corpo=corpo_curto("A verdade impressa resiste ao ruído passageiro.", 4,
                               "A verdade impressa resiste ao ruído passageiro.")),
        dict(titulo="Câmara aprova texto-base da reforma administrativa",
             subtitulo="Proposta segue para análise do Senado com mudanças em carreiras, avaliação de desempenho e regras de transição.",
             categoria="Política", autor="Teresa Castelo", status="publicado", destaque=False,
             etiquetas="#Congresso, #ReformaAdministrativa", quando=(4, 0), leituras=9300, capa=True,
             legenda="Plenário durante a votação.", credito="Agência Câmara",
             corpo=corpo_curto("Por maioria de votos, os deputados aprovaram o texto-base na madrugada desta quarta-feira.", 4,
                               None, ["Avaliação periódica de desempenho", "Regras de transição para servidores atuais", "Limite para pagamentos acima do teto"])),
        dict(titulo="Selic é mantida e mercado ajusta projeções para o fim do ano",
             subtitulo="Comitê cita incertezas externas e inflação de serviços ainda resistente para justificar a manutenção da taxa básica de juros.",
             categoria="Economia & Negócios", autor="Henrique Alcântara", status="publicado", destaque=False,
             etiquetas="#Selic, #Juros", quando=(6, 0), leituras=3100, capa=False,
             corpo=corpo_curto("O Comitê de Política Monetária decidiu por unanimidade manter a taxa básica de juros.", 3)),
        dict(titulo="Seleção feminina estreia com vitória nas eliminatórias",
             subtitulo="Time controla a partida e vence com dois gols no segundo tempo diante de estádio lotado.",
             categoria="Esportes & Lazer", autor="Sofia Ramalho", status="publicado", destaque=False,
             etiquetas="#Futebol, #Seleção", quando=(9, 0), leituras=2200, capa=False,
             corpo=corpo_curto("A equipe brasileira fez uma estreia segura e somou os primeiros três pontos.", 3)),
        dict(titulo="Crônica: o último bonde da Rua das Flores",
             subtitulo="Uma memória de infância sobre a cidade que mudou de ritmo.",
             categoria="Cultura & Artes", autor="Roberto Fontes", status="publicado", destaque=False,
             etiquetas="#Crônica, #Memória", quando=("fixo", 400, "18:15"), leituras=640, capa=False,
             corpo=corpo_curto("Matéria publicada há mais de um ano: testa o formato de data com o ano.", 2)),
        dict(titulo="Nova rota de investigação aponta fraudes em contratos públicos",
             subtitulo="Cruzamento de bases abertas revela padrões repetidos em licitações de pequeno valor.",
             categoria="Política", autor="Sofia Ramalho", status="revisao", destaque=False,
             etiquetas="#Investigação, #Dados", quando=(0, 1), leituras=0, capa=False,
             corpo=corpo_curto("A apuração aguarda a revisão da mesa de cópia jurídica antes de ir para as chapas.", 3)),
        dict(titulo="Mercado de carbono: o que muda para as exportadoras brasileiras",
             subtitulo="Novas regras europeias criam custo adicional para produtos de alta intensidade de emissões.",
             categoria="Meio Ambiente & Clima", autor="Henrique Alcântara", status="revisao", destaque=False,
             etiquetas="#Carbono, #Exportações", quando=(1, 2), leituras=0, capa=False,
             corpo=corpo_curto("Exportadores precisarão reportar as emissões embutidas em cada lote.", 3)),
        dict(titulo="Pauta: cobertura especial das eleições legislativas europeias",
             subtitulo=None,
             categoria="Mundo & Diplomacia", autor="Gabriel Esteves", status="em_pauta", destaque=False,
             etiquetas="#Pauta, #Europa", quando=(0, 0), leituras=0, capa=False,
             corpo="Pauta aberta: definir correspondentes em Bruxelas e Berlim e organizar o plantão de apuração."),
        dict(titulo="Perfil do novo presidente do banco central",
             subtitulo=None,
             categoria="Economia & Negócios", autor="Henrique Alcântara", status="rascunho", destaque=False,
             etiquetas="", quando=(0, 3), leituras=0, capa=False, corpo=""),
        dict(titulo="Estudo comparativo internacional sobre os efeitos da simplificação tributária nas pequenas empresas entre 2010 e 2024",
             subtitulo="Título no limite de 120 caracteres: testa o contador e a quebra de linha nos cartões.",
             categoria="Economia & Negócios", autor="Carlos Eduardo Silva", status="rascunho", destaque=False,
             etiquetas="#Estudo", quando=(2, 5), leituras=0, capa=False,
             corpo=corpo_curto("Versão preliminar para revisão da editoria.", 2)),
        dict(titulo="Embargada: balanço anual das exportações será divulgado na próxima semana",
             subtitulo="Matéria publicada com data de emissão no futuro: o editor deve mostrar o embargo como ativo.",
             categoria="Economia & Negócios", autor="Carlos Eduardo Silva", status="publicado", destaque=False,
             etiquetas="#Embargo, #Exportações", quando=("fixo", -3, "09:00"), leituras=0, capa=False,
             corpo=corpo_curto("Os números só podem ser divulgados após o horário de liberação combinado com o órgão oficial.", 3)),
        dict(titulo="Ação & Reação: 100% de aprovação, “aspas curvas” e _sublinhados_ no debate",
             subtitulo="Matéria de teste para busca, escape de HTML e links seguros.",
             categoria="Opinião & Artigos", autor="Roberto Fontes", status="publicado", destaque=False,
             etiquetas="#Teste, #Acentuação", quando=(8, 0), leituras=120, capa=False, corpo=CORPO_ESPECIAIS),
        dict(titulo="Dossiê: vinte anos de transformação digital nas redações brasileiras",
             subtitulo="Matéria longa (seis capítulos) para testar rolagem, sumário clicável, ficha de rotativa e exportação.",
             categoria="Tecnologia & Ciência", autor="Beatriz Lins", status="publicado", destaque=False,
             etiquetas="#Dossiê, #Jornalismo, #Tecnologia", quando=(12, 0), leituras=1750, capa=True,
             legenda="Linha do tempo da digitalização das redações.", credito="Arquivo NewsManager",
             corpo=corpo_dossie(), inline=True),
    ]


def titulos_do_seed():
    return [m["titulo"] for m in materias()]


# ---------------------------------------------------------------------------
# Utilitários
# ---------------------------------------------------------------------------
def quando_para_data(q) -> datetime:
    agora = datetime.now().replace(second=0, microsecond=0)
    if q[0] == "fixo":
        _, dias, hora = q
        h, m = (int(x) for x in hora.split(":"))
        return (agora - timedelta(days=dias)).replace(hour=h, minute=m)
    dias, horas = q
    return agora - timedelta(days=dias, hours=horas)


def id_por(db, tabela, campo, valor):
    linhas = db._rodar(f"SELECT id FROM {tabela} WHERE {campo} = %s LIMIT 1", (valor,), fetch=True)
    return linhas[0]["id"] if linhas else None


def slug(nome: str) -> str:
    base = (nome.lower().replace("ã", "a").replace("â", "a").replace("á", "a").replace("é", "e").replace("ê", "e")
            .replace("í", "i").replace("ó", "o").replace("õ", "o").replace("ç", "c").replace("ú", "u"))
    return re.sub(r"[^a-z0-9]+", ".", base).strip(".")


def _fonte(tamanho):
    from PIL import ImageFont
    try:
        return ImageFont.load_default(size=tamanho)
    except TypeError:       # Pillow antigo: só existe a fonte pequena padrão
        return ImageFont.load_default()


def gerar_capa(caminho: Path, cor, rotulo: str, tamanho=(1200, 700)):
    """Imagem de capa de teste: degradê na cor da editoria com formas geométricas."""
    from PIL import Image, ImageDraw
    largura, altura = tamanho
    img = Image.new("RGB", tamanho, cor)
    desenho = ImageDraw.Draw(img, "RGBA")
    for y in range(altura):                      # degradê vertical para escuro
        fator = y / altura
        desenho.line([(0, y), (largura, y)], fill=(0, 0, 0, int(150 * fator)))
    desenho.ellipse([largura * 0.62, -altura * 0.2, largura * 1.15, altura * 0.55], fill=(255, 255, 255, 38))
    desenho.rectangle([largura * 0.06, altura * 0.62, largura * 0.52, altura * 0.66], fill=(255, 255, 255, 170))
    desenho.rectangle([largura * 0.06, altura * 0.70, largura * 0.36, altura * 0.73], fill=(255, 255, 255, 110))
    desenho.text((largura * 0.06, altura * 0.18), rotulo.upper(), fill=(255, 255, 255, 235), font=_fonte(64))
    img.save(caminho, "JPEG", quality=88)


def gerar_avatar(caminho: Path, cor, nome: str, lado=400):
    from PIL import Image, ImageDraw
    img = Image.new("RGB", (lado, lado), cor)
    desenho = ImageDraw.Draw(img, "RGBA")
    desenho.ellipse([lado * 0.2, lado * 0.12, lado * 0.8, lado * 0.62], fill=(255, 255, 255, 60))
    desenho.ellipse([lado * 0.05, lado * 0.62, lado * 0.95, lado * 1.4], fill=(255, 255, 255, 40))
    iniciais = "".join(p[0] for p in nome.split()[:2]).upper()
    desenho.text((lado * 0.34, lado * 0.30), iniciais, fill=(255, 255, 255, 240), font=_fonte(int(lado * 0.28)))
    img.save(caminho, "JPEG", quality=88)


COR_DA_CATEGORIA = {"rubro": (139, 30, 30), "azul": (79, 94, 129), "sepia": (90, 68, 38), "carvao": (40, 40, 34)}


def importar(caminho: Path, pasta: str):
    try:
        return gerenciador_midia.importar(caminho, pasta)
    except ErroMidia as erro:
        print(f"  ! imagem ignorada ({erro})")
        return None


# ---------------------------------------------------------------------------
# Popular
# ---------------------------------------------------------------------------
def _popular_sem_notificacoes(db, logger, com_imagens=True, autosave=False, volume=0):
    cs = CategoriaService(db, logger)
    au = AutorService(db, logger, gerenciador_midia)
    ns = NoticiaService(db, logger, gerenciador_midia)
    if com_imagens and not pillow_disponivel():
        print("! Pillow não está instalado: seguindo sem imagens (pip install pillow para testá-las).")
        com_imagens = False
    criadas = {"categorias": 0, "autores": 0, "noticias": 0}

    print("Editorias:")
    cats = {}
    cores_cat = {nome: cor for nome, _d, cor, _s in CATEGORIAS}
    for nome, descricao, cor, status in CATEGORIAS:
        existente = id_por(db, "categorias", "nome", nome)
        if existente:
            cats[nome] = existente
            print(f"  = {nome} (já existia)")
            continue
        r = cs.criar(nome, descricao, cor, status)
        if not r.ok:
            print(f"  ! {nome}: {r.mensagem}")
            continue
        cats[nome] = r.dados
        criadas["categorias"] += 1
        print(f"  + {nome}")

    print("Autores:")
    autores = {}
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        for nome, funcao, cargo, registro, status, foto, email, bio, cor in AUTORES:
            existente = id_por(db, "autores", "nome", nome)
            if existente:
                autores[nome] = existente
                print(f"  = {nome} (já existia)")
                continue
            caminho_foto = None
            if com_imagens and foto:
                gerar_avatar(tmp / f"{slug(nome)}.jpg", cor, nome)
                caminho_foto = importar(tmp / f"{slug(nome)}.jpg", "autores")
            r = au.criar(nome, f"{slug(nome)}@{DOMINIO_EMAIL}" if email else "", funcao, cargo or "",
                         registro or "", status, bio or "", caminho_foto)
            if not r.ok:
                print(f"  ! {nome}: {r.mensagem}")
                continue
            autores[nome] = r.dados
            criadas["autores"] += 1
            print(f"  + {nome}{' (com foto)' if caminho_foto else ''}")

        print("Matérias:")
        for m in materias():
            if id_por(db, "noticias", "titulo", m["titulo"]):
                print(f"  = {m['titulo'][:70]} (já existia)")
                continue
            if m["categoria"] not in cats or m["autor"] not in autores:
                print(f"  ! {m['titulo'][:60]}: editoria ou autor ausente")
                continue
            capa = None
            corpo = m["corpo"]
            if com_imagens and m.get("capa"):
                gerar_capa(tmp / "capa.jpg", COR_DA_CATEGORIA.get(cores_cat[m["categoria"]], (139, 30, 30)), m["categoria"])
                capa = importar(tmp / "capa.jpg", "noticias")
            if m.get("inline"):
                if com_imagens:
                    gerar_capa(tmp / "inline.jpg", (70, 70, 60), "Imagem no texto", (900, 500))
                    caminho = importar(tmp / "inline.jpg", "noticias")
                    corpo = corpo.replace("__IMAGEM_INLINE__", caminho) if caminho else re.sub(r"!\[[^\]]*\]\(__IMAGEM_INLINE__\)\n?", "", corpo)
                else:
                    corpo = re.sub(r"!\[[^\]]*\]\(__IMAGEM_INLINE__\)\n?", "", corpo)
            r = ns.criar(
                m["titulo"], cats[m["categoria"]], autores[m["autor"]], corpo, m.get("subtitulo") or "",
                m["status"], m["destaque"], m["etiquetas"], quando_para_data(m["quando"]),
                capa, m.get("legenda") or "", m.get("credito") or "")
            if not r.ok:
                print(f"  ! {m['titulo'][:60]}: {r.mensagem}")
                if capa:
                    ns.descartar_imagem_orfa(capa)
                continue
            if m["leituras"]:
                db._rodar("UPDATE noticias SET leituras = %s WHERE id = %s", (m["leituras"], r.dados), commit=True)
            criadas["noticias"] += 1
            print(f"  + [{m['status']:<9}] {m['titulo'][:70]}")

    criadas["noticias"] += popular_volume(db, logger, volume)

    if autosave:
        pasta = RAIZ / "rascunhos"
        pasta.mkdir(exist_ok=True)
        arquivo = pasta / "autosave_novo.json"
        dados = dict(titulo=MARCA_AUTOSAVE, subtitulo="Criado pelo seed para testar a recuperação",
                     conteudo="## Texto recuperado\nSe você está lendo isto no editor, a **recuperação do auto-salvamento** funcionou.",
                     categoria_id=None, autor_id=None, data=datetime.now().strftime("%d/%m/%Y %H:%M"),
                     status="rascunho", destaque=False, etiquetas="#Teste", imagem=None,
                     imagem_legenda="", imagem_credito="", _salvo_em=datetime.now().isoformat(timespec="seconds"))
        arquivo.write_text(json.dumps(dados, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"Auto-salvamento de exemplo criado em {arquivo.relative_to(RAIZ)} (abra '+ Nova matéria' para recuperá-lo).")

    print(f"\nCriados agora: {criadas['categorias']} editorias, {criadas['autores']} autores, {criadas['noticias']} matérias.")
    return criadas


def popular(db, logger, com_imagens=True, autosave=False, volume=0):
    """Cria os dados de teste. As notificações automáticas ficam silenciadas durante a carga (seriam
    centenas) e, no fim, entra um conjunto escolhido de despachos de exemplo."""
    with silenciar():
        criadas = _popular_sem_notificacoes(db, logger, com_imagens, autosave, volume)
    criadas["notificacoes"] = popular_notificacoes(db, logger)
    return criadas


# ---------------------------------------------------------------------------
# Notificações de exemplo (painel do sino)
# ---------------------------------------------------------------------------
def popular_notificacoes(db, logger):
    """Despachos variados (urgente, publicação, estrutura, revisão, arquivo, pauta, antigos)."""
    agora = datetime.now().replace(microsecond=0)
    manchete = id_por(db, "noticias", "titulo", "Reforma Tributária e os Novos Desafios Estruturais para o Varejo Nacional")
    ia = id_por(db, "noticias", "titulo", "Avanços em Inteligência Artificial Redefinem a Produção de Notícias")
    cat_tec = id_por(db, "categorias", "nome", "Tecnologia & Ciência")
    ontem = (agora - timedelta(days=1)).replace(hour=22, minute=0)
    exemplos = [
        ("furo", "Plantão do Telégrafo: Coletiva do Banco Central",
         "Correspondência de Brasília: coletiva extraordinária do Banco Central convocada para as 16h30 sobre política cambial.",
         "Telégrafo", "URGENTE • PRIORIDADE ZERO", True, "noticia", manchete, agora - timedelta(hours=1)),
        ("publicacao", "Reforma Tributária e Impactos nos Serviços",
         "A peça de Carlos Eduardo Silva acabou de ser carimbada para circulação digital com aprovação da editoria de economia.",
         "Economia", "AUTOR: CARLOS EDUARDO SILVA", False, "noticia", manchete, agora - timedelta(minutes=12)),
        ("estrutura", "Categoria Atualizada no Mastro",
         "A editoria Tecnologia & Ciência teve sua taxonomia revisada pelo Editor-Chefe.",
         None, "DESPACHO DA CHEFIA", False, "categoria", cat_tec, agora - timedelta(minutes=45)),
        ("revisao", "Revisão Ortográfica Concluída",
         "A copydesk revisou o texto integral de “Avanços em Inteligência Artificial” sem pendências terminológicas.",
         None, "LIBERAÇÃO CONCEDIDA", False, "noticia", ia, agora - timedelta(hours=3)),
        ("arquivo", "Backup do Acervo Histórico Finalizado",
         "O espelhamento das edições encadernadas de 1850 a 1980 foi validado no cofre digital de segurança redundante.",
         "Arquivo central", "ARQUIVO & MEMÓRIA", False, None, None, ontem),
        ("pauta", "Pauta: cobertura especial das eleições europeias",
         "Nova pauta aberta na editoria de Mundo & Diplomacia, sob responsabilidade de Gabriel Esteves.",
         "Mundo & Diplomacia", "FILA DE APURAÇÃO", False, None, None, agora - timedelta(days=3)),
        ("publicacao", "Seleção feminina estreia com vitória nas eliminatórias",
         "A peça de Sofia Ramalho foi carimbada para circulação digital na editoria de Esportes & Lazer.",
         "Esportes & Lazer", "AUTOR: SOFIA RAMALHO", False, None, None, agora - timedelta(days=9)),
        ("arquivo", "Matéria Removida do Acervo",
         "A matéria “Crônica de teste do ano passado” foi excluída pela chefia há mais de um ano (exemplo de data antiga).",
         None, "ARQUIVO & MEMÓRIA", False, None, None, agora - timedelta(days=400)),
    ]
    criadas = 0
    for tipo, titulo, mensagem, etiqueta, rodape, urgente, alvo_tipo, alvo_id, quando in exemplos:
        if db._rodar("SELECT id FROM notificacoes WHERE titulo = %s AND ator = %s LIMIT 1", (titulo, ATOR_SEED), fetch=True):
            continue
        db.criar_notificacao(tipo, titulo, mensagem, etiqueta, rodape, urgente,
                             alvo_tipo if alvo_id else None, alvo_id, None, ATOR_SEED, quando)
        criadas += 1
    print(f"Notificações de exemplo: {criadas} criadas (autor da ação: {ATOR_SEED}).")
    return criadas


# ---------------------------------------------------------------------------
# Volume: matérias extras para os gráficos
# ---------------------------------------------------------------------------
TEMAS_VOLUME = {
    "Política": ["Boletim do plenário", "Ata da comissão", "Resumo da sessão", "Balanço legislativo"],
    "Economia & Negócios": ["Fechamento dos mercados", "Indicador da semana", "Balanço trimestral", "Câmbio e juros"],
    "Tecnologia & Ciência": ["Descoberta em laboratório", "Lançamento tecnológico", "Estudo publicado", "Inovação aplicada"],
    "Cultura & Artes": ["Estreia da semana", "Exposição em cartaz", "Crítica do fim de semana", "Agenda cultural"],
    "Mundo & Diplomacia": ["Despacho internacional", "Acordo bilateral", "Cúpula de líderes", "Panorama global"],
    "Opinião & Artigos": ["Artigo de opinião", "Carta do leitor", "Coluna de análise", "Ponto de vista"],
    "Esportes & Lazer": ["Resultado da rodada", "Análise tática", "Bastidores do campeonato"],
    "Meio Ambiente & Clima": ["Alerta climático", "Relatório ambiental", "Energia limpa em pauta"],
}
PESO_CATEGORIA = {"Política": 30, "Economia & Negócios": 24, "Tecnologia & Ciência": 20, "Cultura & Artes": 14,
                  "Mundo & Diplomacia": 12, "Opinião & Artigos": 9, "Esportes & Lazer": 5, "Meio Ambiente & Clima": 6}
AUTORES_VOLUME = {"Teresa Castelo": 3, "Henrique Alcântara": 3, "Beatriz Lins": 2, "Gabriel Esteves": 2,
                  "Sofia Ramalho": 1.5, "Roberto Fontes": 1, "Carlos Eduardo Silva": 2, "Mariana Alencar": 1}
PESO_DIA_SEMANA = [1.0, 1.5, 1.7, 1.6, 1.4, 0.5, 0.25]      # segunda ... domingo (picos: terça e quarta)


def popular_volume(db, logger, quantidade):
    """Cria `quantidade` matérias curtas espalhadas pelos últimos 120 dias (sempre as mesmas, por usar
    uma semente fixa). Joana Freitas fica sem matérias de propósito (teste de exclusão)."""
    if quantidade <= 0:
        return 0
    ns = NoticiaService(db, logger, gerenciador_midia)
    cats = {n: id_por(db, "categorias", "nome", n) for n in PESO_CATEGORIA}
    autores = {n: id_por(db, "autores", "nome", n) for n in AUTORES_VOLUME}
    if not all(cats.values()) or not all(autores.values()):
        print("! Volume ignorado: rode o seed completo antes (faltam editorias ou autores).")
        return 0
    agora = datetime.now().replace(second=0, microsecond=0)
    criadas = 0
    for numero in range(1, quantidade + 1):
        rnd = random.Random(2024 * 1000 + numero)    # cada matéria tem a própria semente: rodar de novo não duplica
        while True:      # sorteia um dia respeitando o peso de cada dia da semana
            data = (agora - timedelta(days=rnd.randint(0, 119))).replace(hour=rnd.randint(7, 21), minute=rnd.randint(0, 59))
            if data < agora and rnd.random() <= PESO_DIA_SEMANA[data.weekday()] / max(PESO_DIA_SEMANA):
                break
        categoria = rnd.choices(list(PESO_CATEGORIA), weights=list(PESO_CATEGORIA.values()))[0]
        autor = rnd.choices(list(AUTORES_VOLUME), weights=list(AUTORES_VOLUME.values()))[0]
        titulo = f"{PREFIXO_VOLUME}{numero:03d} — {rnd.choice(TEMAS_VOLUME[categoria])}"
        if id_por(db, "noticias", "titulo", titulo):
            continue
        sorteio = rnd.random()
        status = "publicado" if sorteio < 0.88 else "revisao" if sorteio < 0.94 else "rascunho" if sorteio < 0.98 else "em_pauta"
        corpo = corpo_curto(titulo, rnd.randint(1, 6))
        r = ns.criar(titulo, cats[categoria], autores[autor], corpo, "", status, False, "#Volume", data)
        if not r.ok:
            print(f"  ! {titulo}: {r.mensagem}")
            continue
        if status == "publicado":
            leituras = int(rnd.lognormvariate(6.2, 0.9) * (1.6 if categoria == "Política" else 1.0))
            db._rodar("UPDATE noticias SET leituras = %s WHERE id = %s", (leituras, r.dados), commit=True)
        criadas += 1
    print(f"Volume: {criadas} matérias extras criadas (títulos começam com \"{PREFIXO_VOLUME}\").")
    return criadas


# ---------------------------------------------------------------------------
# Limpar (só o que o seed criou)
# ---------------------------------------------------------------------------
def limpar(db, logger):
    with silenciar():     # apagar não deve gerar centenas de "matéria removida"
        removidos = _limpar(db, logger)
    db.excluir_notificacoes_do_ator(ATOR_SEED)
    return removidos


def _limpar(db, logger):
    cs = CategoriaService(db, logger)
    au = AutorService(db, logger, gerenciador_midia)
    ns = NoticiaService(db, logger, gerenciador_midia)
    removidos = {"noticias": 0, "autores": 0, "categorias": 0}
    for linha in db._rodar("SELECT id FROM noticias WHERE titulo LIKE %s", (PREFIXO_VOLUME + "%",), fetch=True):
        if ns.excluir(linha["id"]).ok:
            removidos["noticias"] += 1
    for titulo in titulos_do_seed():
        id_ = id_por(db, "noticias", "titulo", titulo)
        if id_ and ns.excluir(id_).ok:
            removidos["noticias"] += 1
    for nome, *_ in AUTORES:
        id_ = id_por(db, "autores", "nome", nome)
        if id_ and au.excluir(id_).ok:          # autor com matérias de outras pessoas é mantido
            removidos["autores"] += 1
    for nome, *_ in CATEGORIAS:
        if nome in CATEGORIAS_DO_SCHEMA:
            continue
        id_ = id_por(db, "categorias", "nome", nome)
        if id_ and cs.excluir(id_).ok:          # editoria com matérias de outras pessoas é mantida
            removidos["categorias"] += 1
    try:
        _limpar_clipping_seed(db)       # sobras de uma verificação de clipping interrompida
    except ErroBanco:
        pass
    arquivo = RAIZ / "rascunhos" / "autosave_novo.json"
    try:
        if arquivo.is_file() and json.loads(arquivo.read_text(encoding="utf-8")).get("titulo") == MARCA_AUTOSAVE:
            arquivo.unlink()
            print("Auto-salvamento de exemplo removido.")
    except (OSError, ValueError):
        pass
    print(f"Removidos: {removidos['noticias']} matérias, {removidos['autores']} autores, {removidos['categorias']} editorias.")
    return removidos


# ---------------------------------------------------------------------------
# Verificação automática
# ---------------------------------------------------------------------------
class Verificador:
    def __init__(self):
        self.ok = 0
        self.falhas = []
        self.avisos = []

    def checar(self, nome, condicao, detalhe=""):
        if condicao:
            self.ok += 1
            print(f"  OK     {nome}")
        else:
            self.falhas.append(nome)
            print(f"  FALHA  {nome}" + (f"  -> {detalhe}" if detalhe else ""))

    def avisar(self, nome, detalhe=""):
        self.avisos.append(nome)
        print(f"  AVISO  {nome}" + (f"  -> {detalhe}" if detalhe else ""))


def _arquivos_de_midia():
    arquivos = set()
    for pasta in ("noticias", "autores"):
        base = gerenciador_midia.base / pasta
        if base.is_dir():
            arquivos |= {f"{pasta}/{p.name}" for p in base.iterdir() if p.is_file()}
    return arquivos


def verificar(db, logger):
    with silenciar():     # as verificações criam e apagam itens temporários: sem notificações
        return _verificar(db, logger)


def _verificar(db, logger):
    v = Verificador()
    cs = CategoriaService(db, logger)
    au = AutorService(db, logger, gerenciador_midia)
    ns = NoticiaService(db, logger, gerenciador_midia)
    ids = {titulo: id_por(db, "noticias", "titulo", titulo) for titulo in titulos_do_seed()}
    if not any(ids.values()):
        print("Nenhuma matéria do seed encontrada. Rode `python seed.py` antes de verificar.")
        return v

    print("\nBanco e esquema")
    try:
        for tabela, colunas in {"categorias": ["descricao", "cor", "status"],
                                "autores": ["bio", "funcao", "cargo", "registro", "status", "foto"],
                                "noticias": ["subtitulo", "status", "destaque", "etiquetas", "leituras",
                                             "imagem", "imagem_legenda", "imagem_credito"]}.items():
            faltando = [c for c in colunas if not db._coluna_existe(tabela, c)]
            v.checar(f"colunas novas em {tabela}", not faltando, f"faltando: {faltando}")
        v.checar("data_publicacao é DATETIME", db._tipo_coluna("noticias", "data_publicacao") == "datetime",
                 str(db._tipo_coluna("noticias", "data_publicacao")))
    except ErroBanco as e:
        v.checar("consulta ao esquema", False, str(e))

    print("\nCategorias")
    r = cs.listar()
    v.checar("listar categorias", r.ok and len(r.dados) >= len(CATEGORIAS) - 1, r.mensagem)
    resumo = cs.resumo()
    v.checar("cartões de resumo", resumo.ok and resumo.dados["mais_ativa"] is not None and resumo.dados["total_noticias"] >= 15,
             str(resumo.dados if resumo.ok else resumo.mensagem))
    v.checar("busca por descrição", any(c["nome"] == "Tecnologia & Ciência" for c in cs.listar("inteligência artificial").dados or []))
    v.checar("nome duplicado é barrado", not cs.criar("tecnologia & ciência", "Descrição qualquer válida").ok)
    v.checar("categoria com matérias não pode ser excluída", not cs.excluir(id_por(db, "categorias", "nome", "Economia & Negócios")).ok)
    temp = cs.criar("Temporária do verificador", "Criada e removida pelo seed", "azul")
    v.checar("criar categoria", temp.ok, temp.mensagem)
    if temp.ok:
        v.checar("atualizar categoria", cs.atualizar(temp.dados, "Temporária do verificador", "Descrição alterada", "sepia", "em_revisao").ok)
        v.checar("excluir categoria vazia", cs.excluir(temp.dados).ok)

    print("\nAutores")
    todos = au.contagem_por_funcao()
    v.checar("contagem por função", todos.ok and todos.dados["todos"] >= len(AUTORES) and todos.dados["colunista"] >= 2, str(todos.dados))
    v.checar("filtro por função", all(a["funcao"] == "colunista" for a in au.listar("", "colunista").dados))
    v.checar("busca por registro (MTB)", any(a["nome"] == "Teresa Castelo" for a in au.listar("0031849").dados))
    teresa = au.listar("Teresa").dados[0]
    v.checar("autor com total de matérias e última publicação", teresa["total_noticias"] >= 1 and teresa["ultima_publicacao"] is not None, str(teresa))
    v.checar("autor com matérias não pode ser excluído", not au.excluir(teresa["id"]).ok)
    v.checar("e-mail duplicado é barrado", not au.criar("Outra Pessoa", f"teresa.castelo@{DOMINIO_EMAIL}").ok)
    v.checar("e-mail inválido é barrado", not au.criar("Outra Pessoa", "sem-arroba").ok)
    temp_autor = au.criar("Autor temporário do verificador", "", "colunista")
    v.checar("criar e excluir autor sem matérias", temp_autor.ok and au.excluir(temp_autor.dados).ok)
    materias_autor = au.materias_do_autor(teresa["id"])
    v.checar("matérias do autor (botão 'Ver matérias')", materias_autor.ok and len(materias_autor.dados) >= 1)
    sem_materias = id_por(db, "autores", "nome", "Joana Freitas")
    v.checar("autor sem matérias existe e pode ser excluído (não excluído aqui)", sem_materias is not None and au.obter(sem_materias).ok)

    print("\nNotícias: feed, filtros e busca")
    pag1 = ns.listar(pagina=1, por_pagina=6)
    v.checar("feed lista matérias", pag1.ok and pag1.dados["total"] >= 18, pag1.mensagem)
    esperado = math.ceil(pag1.dados["total"] / 6)
    v.checar("paginação", pag1.dados["paginas"] == esperado and len(pag1.dados["itens"]) == 6, f"{pag1.dados['paginas']} páginas")
    ultima = ns.listar(pagina=esperado + 5, por_pagina=6)
    v.checar("página fora do limite é ajustada", ultima.dados["pagina"] == esperado)
    for status, minimo in (("publicado", 11), ("revisao", 2), ("em_pauta", 1), ("rascunho", 2)):
        v.checar(f"filtro por estado: {status}", ns.listar(status=status).dados["total"] >= minimo)
    v.checar("filtro por editoria", all(i["categoria"] == "Política" for i in ns.listar(categoria_id=id_por(db, "categorias", "nome", "Política"), por_pagina=50).dados["itens"]))
    mais_lidas = ns.listar(ordem="lidas", por_pagina=3).dados["itens"]
    v.checar("ordenar por mais lidas", mais_lidas and mais_lidas[0]["leituras"] >= mais_lidas[-1]["leituras"] and mais_lidas[0]["leituras"] >= 14800,
             str([i["leituras"] for i in mais_lidas]))
    por_titulo = [i["titulo"] for i in ns.listar(ordem="titulo", por_pagina=50).dados["itens"]]
    v.checar("ordenar por título (A–Z)", len(por_titulo) >= 18 and por_titulo[0].lower() <= por_titulo[-1].lower(), str(por_titulo[:2]))
    v.checar("busca por título", ns.listar(termo="Selic").dados["total"] >= 1)
    v.checar("busca por autor", ns.listar(termo="Teresa Castelo").dados["total"] >= 1)
    v.checar("busca por etiqueta", ns.listar(termo="IBS").dados["total"] >= 1)
    busca_pct = ns.listar(termo="100%", por_pagina=50)
    v.checar("busca com '%' é tratada como texto (não casa tudo)", 1 <= busca_pct.dados["total"] <= 3, f"total={busca_pct.dados['total']}")
    busca_sub = ns.listar(termo="_sublinhados_", por_pagina=50)
    v.checar("busca com '_' é tratada como texto", 1 <= busca_sub.dados["total"] <= 2, f"total={busca_sub.dados['total']}")
    v.checar("busca sem resultado", ns.listar(termo="zzzzinexistentezzzz").dados["total"] == 0)
    v.checar("feed não traz o corpo inteiro (só resumo)", "conteudo" not in pag1.dados["itens"][0] and "resumo" in pag1.dados["itens"][0])

    print("\nNotícias: painel lateral e datas")
    rs = ns.resumo()
    v.checar("resumo da tiragem", rs.ok and rs.dados["publicadas"] >= 11 and rs.dados["pendentes_revisao"] >= 2, str(rs.dados if rs.ok else rs.mensagem))
    v.checar("distribuição por seção (máx. 5)", rs.ok and 1 <= len(rs.dados["distribuicao"]) <= 5)
    v.checar("leituras somadas", rs.ok and rs.dados["leituras"] >= 60000, str(rs.dados.get("leituras") if rs.ok else ""))
    embargada = ns.obter(ids["Embargada: balanço anual das exportações será divulgado na próxima semana"])
    from app.noticias import interpretar_data
    v.checar("matéria embargada tem data futura e está publicada",
             embargada.ok and embargada.dados["status"] == "publicado" and interpretar_data(embargada.dados["data_publicacao"]) > datetime.now())
    antiga = ns.obter(ids["Crônica: o último bonde da Rua das Flores"])
    v.checar("matéria de mais de um ano", antiga.ok and (datetime.now() - interpretar_data(antiga.dados["data_publicacao"])).days > 300)
    longo = ns.obter(ids["Estudo comparativo internacional sobre os efeitos da simplificação tributária nas pequenas empresas entre 2010 e 2024"])
    v.checar("título com ~120 caracteres foi aceito", longo.ok and 100 <= len(longo.dados["titulo"]) <= 120, str(len(longo.dados["titulo"]) if longo.ok else ""))
    vazio = ns.obter(ids["Perfil do novo presidente do banco central"])
    v.checar("rascunho sem texto foi aceito", vazio.ok and not (vazio.dados["conteudo"] or "").strip())
    v.checar("rascunho não pode ser manchete", not ns.criar("Tentativa de manchete rascunho", 1, 1, "x", status="rascunho", destaque=True).ok)
    v.checar("publicar sem texto é barrado", not ns.criar("Tentativa sem texto algum", 1, 1, "curto", status="publicado").ok)

    print("\nNotícias: leitura, formatação e exportação")
    manchete = ns.obter(ids["Reforma Tributária e os Novos Desafios Estruturais para o Varejo Nacional"])
    corpo = manchete.dados["conteudo"] if manchete.ok else ""
    tipos = {b.tipo for b in blocos(corpo)}
    v.checar("texto tem todos os tipos de bloco", {"h2", "h3", "paragrafo", "citacao", "item", "item_num", "regra"} <= tipos, str(tipos))
    v.checar("sumário (intertítulos)", len(intertitulos(corpo)) >= 3)
    v.checar("texto simples não tem marcadores", "**" not in texto_simples(corpo) and "##" not in texto_simples(corpo))
    dossie = ns.obter(ids["Dossiê: vinte anos de transformação digital nas redações brasileiras"])
    simples = texto_simples(dossie.dados["conteudo"]) if dossie.ok else ""
    palavras = contar_palavras(simples)
    flesch = indice_flesch(simples)
    v.checar("matéria longa: palavras e colunas", palavras >= 800, f"{palavras} palavras, {colunas_estimadas(palavras)}")
    v.checar("legibilidade Flesch calculada", flesch is not None, f"{flesch} ({classificar_flesch(flesch)})")
    especiais = ns.obter(ids["Ação & Reação: 100% de aprovação, “aspas curvas” e _sublinhados_ no debate"])
    html_ = pagina_html(especiais.dados["titulo"], especiais.dados["subtitulo"] or "", "meta", especiais.dados["conteudo"]) if especiais.ok else ""
    v.checar("HTML exportado escapa <script>", "<script>alert" not in html_ and "&lt;script&gt;" in html_)
    v.checar("HTML exportado não gera link javascript:", 'href="javascript' not in html_ and 'href="https://exemplo.com"' in html_)
    rel = ns.relacionadas(ids["Reforma Tributária e os Novos Desafios Estruturais para o Varejo Nacional"])
    v.checar("leituras suplementares (mesma editoria, publicadas, sem a própria)",
             rel.ok and 1 <= len(rel.dados) <= 3 and all(i["categoria"] == "Economia & Negócios" and i["id"] != manchete.dados["id"] for i in rel.dados),
             str([i["titulo"][:30] for i in rel.dados]) if rel.ok else rel.mensagem)
    antes = ns.obter(ids["Selic é mantida e mercado ajusta projeções para o fim do ano"]).dados["leituras"]
    ns.registrar_leitura(ids["Selic é mantida e mercado ajusta projeções para o fim do ano"])
    v.checar("registrar leitura soma 1", ns.obter(ids["Selic é mantida e mercado ajusta projeções para o fim do ano"]).dados["leituras"] == antes + 1)
    db._rodar("UPDATE noticias SET leituras = %s WHERE id = %s", (antes, ids["Selic é mantida e mercado ajusta projeções para o fim do ano"]), commit=True)

    print("\nImagens")
    seed_tem_imagens = any(i["imagem"] for i in ns.listar(por_pagina=100).dados["itens"])
    if not pillow_disponivel():
        v.avisar("Pillow não instalado", "as verificações de imagem foram puladas (pip install pillow)")
    elif not seed_tem_imagens:
        v.avisar("nenhuma matéria com capa", "o seed foi rodado com --sem-imagens (ou sem Pillow); rode `python seed.py --recriar` para testar imagens")
    else:
        com_capa = [i for i in ns.listar(por_pagina=100).dados["itens"] if i["imagem"]]
        v.checar("matérias com capa", len(com_capa) >= 5, f"{len(com_capa)} com capa")
        v.checar("arquivos de capa existem no disco", all(gerenciador_midia.existe(i["imagem"]) for i in com_capa),
                 str([i["imagem"] for i in com_capa if not gerenciador_midia.existe(i["imagem"])]))
        capa_pil = gerenciador_midia.preparar(com_capa[0]["imagem"], 320, 140) if com_capa else None
        v.checar("capa é recortada no tamanho do cartão", capa_pil is not None and capa_pil.size == (320, 140))
        fotos = [a for a in au.listar().dados if a["foto"]]
        v.checar("autores com foto", len(fotos) >= 5 and all(gerenciador_midia.existe(a["foto"]) for a in fotos), f"{len(fotos)} com foto")
        inline = caminhos_de_imagens(corpo)
        v.checar("imagem no meio do texto existe no disco", bool(inline) and all(gerenciador_midia.existe(p) for p in inline), str(inline))
        referenciados = set()
        for i in ns.listar(por_pagina=100).dados["itens"]:
            n = ns.obter(i["id"]).dados
            if n["imagem"]:
                referenciados.add(n["imagem"])
            referenciados |= caminhos_de_imagens(n["conteudo"])
        referenciados |= {a["foto"] for a in fotos}
        orfaos = _arquivos_de_midia() - referenciados
        if orfaos:
            v.avisar(f"{len(orfaos)} arquivo(s) em midia/ sem uso no banco", ", ".join(sorted(orfaos)[:4]) + ("..." if len(orfaos) > 4 else ""))
        else:
            v.checar("nenhuma imagem órfã em midia/", True)

    verificar_estatisticas(v, db, logger, ns)
    verificar_notificacoes_e_perfil(v, db, logger)
    verificar_tempo_e_clipping(v, db, logger)

    print(f"\nResultado: {v.ok} verificações OK, {len(v.falhas)} falha(s), {len(v.avisos)} aviso(s).")
    for nome in v.falhas:
        print(f"  - FALHA: {nome}")
    return v


def verificar_notificacoes_e_perfil(v, db, logger):
    """Painel de notificações, perfil e preferências — sem alterar nada de usuários reais
    (a leitura é testada com um usuário fictício, depois removido)."""
    print("\nNotificações e perfil")
    try:
        tabelas_ok = all(db._rodar(f"SELECT COUNT(*) AS n FROM {t}", fetch=True) is not None
                         for t in ("notificacoes", "notificacoes_lidas", "preferencias_usuario"))
    except ErroBanco as erro:
        v.checar("tabelas de notificações e preferências existem", False, str(erro))
        return
    v.checar("tabelas de notificações e preferências existem", tabelas_ok)
    fantasma = -987654   # usuário fictício: não mexe no 'lida / não lida' de ninguém
    try:
        ns = NotificacaoService(db, logger, fantasma)
        total = ns.contagens()
        v.checar("contagens do painel", total.ok and total.dados["todas"] >= 1 and total.dados["nao_lidas"] == total.dados["todas"]
                 and total.dados["urgentes"] <= total.dados["todas"], str(total.dados if total.ok else total.mensagem))
        lista = ns.listar("todas", 1, 5)
        v.checar("listagem (mais recentes primeiro)", lista.ok and len(lista.dados["itens"]) >= 1 and all(
            lista.dados["itens"][i]["criado_em"] >= lista.dados["itens"][i + 1]["criado_em"]
            for i in range(len(lista.dados["itens"]) - 1)), lista.mensagem)
        v.checar("tempo relativo e rótulo de tipo nos itens", all(i["tempo"] and i["tipo_rotulo"] for i in lista.dados["itens"]),
                 str([(i["tempo"], i["tipo_rotulo"]) for i in lista.dados["itens"]]))
        urgentes = ns.listar("urgentes", 1, 50)
        v.checar("filtro de urgentes", urgentes.ok and all(i["urgente"] for i in urgentes.dados["itens"]))
        if lista.dados["itens"]:
            primeiro = lista.dados["itens"][0]["id"]
            v.checar("marcar uma como lida", ns.marcar_lida(primeiro).ok and
                     ns.contagens().dados["nao_lidas"] == total.dados["nao_lidas"] - 1)
            v.checar("marcar todas como lidas", ns.marcar_todas_lidas().ok and ns.contagens().dados["nao_lidas"] == 0)
    finally:
        db._rodar("DELETE FROM notificacoes_lidas WHERE usuario_id = %s", (fantasma,), commit=True)
    # preferências (usuário fictício)
    pf = PerfilService(db, logger)
    try:
        padrao = pf.preferencias(fantasma)
        v.checar("preferências padrão", padrao == {"alerta_sonoro": True, "email_urgencia": False,
                                                    "revisao_automatica": False, "polegadas_coluna": False}, str(padrao))
        v.checar("salvar e ler preferências", pf.salvar_preferencias(fantasma, {"revisao_automatica": True}).ok
                 and pf.preferencias(fantasma)["revisao_automatica"] is True)
        v.checar("preferência desconhecida é recusada", not pf.salvar_preferencias(fantasma, {"inventada": True}).ok)
    finally:
        db._rodar("DELETE FROM preferencias_usuario WHERE usuario_id = %s", (fantasma,), commit=True)
    # regras de senha e perfil real (somente leitura)
    regras = avaliar_senha("NovaSenha#2026!", "SenhaAntiga@123", "NovaSenha#2026!")
    v.checar("regras de senha", all(ok for _, ok in regras) and not all(ok for _, ok in avaliar_senha("curta")))
    usuario = db._rodar("SELECT id FROM usuarios ORDER BY id LIMIT 1", fetch=True)
    if usuario:
        perfil = pf.obter(usuario[0]["id"])
        v.checar("perfil do primeiro usuário carrega", perfil.ok and perfil.dados["prontuario"].startswith("NM-")
                 and perfil.dados["materias_publicadas"] >= 0, perfil.mensagem)
        v.checar("dados inválidos são recusados", not pf.salvar_dados(usuario[0]["id"], {"nome": "A"}).ok)
    else:
        v.avisar("nenhum usuário cadastrado", "o perfil real não foi verificado (crie uma conta e rode de novo)")
    contadas = db._rodar("SELECT COUNT(*) AS n FROM notificacoes WHERE ator = %s", (ATOR_SEED,), fetch=True)[0]["n"]
    v.checar("notificações de exemplo do seed existem", int(contadas) >= 1, str(contadas))


def verificar_estatisticas(v, db, logger, ns):
    """Confere a tela de Gráficos: indicadores coerentes entre si e com a listagem de matérias."""
    print("\nEstatísticas (tela de Gráficos)")
    es = EstatisticasService(db, logger)
    agora = datetime.now().replace(microsecond=0)
    resultados = {p: es.consultar(FiltroEstatisticas(p), agora) for p in ("7d", "30d", "90d", "12m", "ano", "tudo")}
    v.checar("consultas por período funcionam", all(r.ok for r in resultados.values()),
             str([p for p, r in resultados.items() if not r.ok]))
    if not all(r.ok for r in resultados.values()):
        return
    totais = [resultados[p].dados["kpis"]["total"] for p in ("7d", "30d", "90d", "tudo")]
    v.checar("períodos mais longos nunca têm menos matérias", totais == sorted(totais), str(totais))
    d = resultados["30d"].dados
    k = d["kpis"]
    v.checar("editorias somam o total", sum(c["total"] for c in d["categorias"]) == k["total"])
    v.checar("percentuais somam 100%", k["total"] == 0 or abs(sum(c["percentual"] for c in d["categorias"]) - 100) < 0.01)
    v.checar("dias da semana somam o total", sum(d["semana"]["totais"]) == k["total"])
    v.checar("série temporal soma o total", sum(d["serie"]["valores"]) == k["total"])
    v.checar("scores dos autores entre 0 e 100", all(0 <= a["score"] <= 100 for a in d["autores"]))
    v.checar("autores somam o total", sum(a["total"] for a in d["autores"]) == k["total"])
    v.checar("indicadores têm sentido", 0 <= k["pct_editorias"] <= 100 and k["editorias_operacao"] <= k["editorias_ativas"]
             and k["media_leituras"] >= 0, str(k))
    v.checar("comparação com o período anterior", k["total_anterior"] is None or isinstance(k["total_anterior"], int))
    v.checar("leitura dos dados gera frases", len(d["insights"]) >= 1 and all(isinstance(f, str) and f for f in d["insights"]))
    tudo = resultados["tudo"].dados
    futuras = db._rodar("SELECT COUNT(*) AS n FROM noticias WHERE status = 'publicado' AND data_publicacao > %s",
                        (agora,), fetch=True)[0]["n"]
    publicadas = ns.listar(status="publicado").dados["total"]
    v.checar("estatística de 'todo o período' bate com o feed (menos as embargadas)",
             tudo["kpis"]["total"] == publicadas - int(futuras), f"{tudo['kpis']['total']} vs {publicadas} - {futuras}")
    v.checar("todo o período não tem comparação", tudo["kpis"]["variacao_total"] is None and tudo["periodo"]["dias"] >= 1)
    # filtros combinados
    if tudo["categorias"] and tudo["categorias"][0]["total"]:
        cat = tudo["categorias"][0]
        f = es.consultar(FiltroEstatisticas("tudo", categoria_id=cat["id"]), agora).dados
        v.checar("filtro de editoria isola a editoria", f["kpis"]["total"] == cat["total"] and
                 [c["nome"] for c in f["categorias"]] == [cat["nome"]])
    if tudo["autores"]:
        aut = tudo["autores"][0]
        f = es.consultar(FiltroEstatisticas("tudo", autor_id=aut["id"]), agora).dados
        v.checar("filtro de jornalista isola o jornalista", f["kpis"]["total"] == aut["total"] and len(f["autores"]) == 1)
    todos = es.consultar(FiltroEstatisticas("tudo", status="todos"), agora).dados["kpis"]["total"]
    v.checar("'todos os estados' tem pelo menos as publicadas", todos >= tudo["kpis"]["total"])
    rascunhos = es.consultar(FiltroEstatisticas("tudo", status="rascunho"), agora).dados["kpis"]["total"]
    v.checar("filtro por estado (rascunho)", rascunhos >= 1, str(rascunhos))
    pers = es.consultar(FiltroEstatisticas("personalizado", inicio=(agora - timedelta(days=10)).date(), fim=agora.date()), agora)
    v.checar("período personalizado", pers.ok and pers.dados["periodo"]["dias"] == 11, pers.mensagem)
    v.checar("período personalizado inválido é recusado", not es.consultar(
        FiltroEstatisticas("personalizado", inicio=agora.date(), fim=(agora - timedelta(days=3)).date()), agora).ok)
    vazio = es.consultar(FiltroEstatisticas("7d", status="em_pauta", categoria_id=id_por(db, "categorias", "nome", "Saúde & Bem-estar") or 0), agora)
    v.checar("recorte vazio não quebra", vazio.ok and vazio.dados["kpis"]["total"] == 0)
    # gráficos e relatório
    try:
        from app.graficos import exportar_pdf, figura_distribuicao, figura_semana, figura_serie
    except ImportError as erro:
        v.avisar("matplotlib não instalado", f"gráficos e PDF não verificados ({erro})")
        return
    figuras = [figura_distribuicao(d["categorias"]), figura_semana(d["semana"]), figura_serie(d["serie"])]
    v.checar("gráficos do matplotlib são criados", all(f.get_axes() for f in figuras))
    with tempfile.TemporaryDirectory() as tmp:
        caminho = Path(tmp) / "relatorio.pdf"
        paginas = exportar_pdf(caminho, d, "verificação do seed")
        v.checar("relatório em PDF (3 páginas)", paginas == 3 and caminho.read_bytes()[:4] == b"%PDF" and caminho.stat().st_size > 5000,
                 f"{caminho.stat().st_size} bytes")
    linhas = es.linhas_csv(d)
    v.checar("dados do CSV", len(linhas) > 10 and linhas[0][0].startswith("Relatório"))


# ---------------------------------------------------------------------------
# Previsão do tempo e Clipping: verificação OFFLINE (fixtures de tests/fixtures)
# ---------------------------------------------------------------------------
FONTE_VERIFICACAO = "seed_verif"      # fonte fictícia: só existe durante a verificação
NOME_FONTE_VERIFICACAO = "Exemplo Seed"
LOCAL_VERIFICACAO = {"nome": "Cidade de Teste", "regiao": "Teste", "pais": "Brasil", "latitude": 0.01,
                     "longitude": 0.01, "fuso": "auto"}
FIXTURES = RAIZ / "tests" / "fixtures"


def _ler_fixture(nome):
    return (FIXTURES / nome).read_bytes()


def _limpar_clipping_seed(db):
    """Remove tudo o que a verificação do clipping cria (também de execuções interrompidas)."""
    for linha in db._rodar("SELECT importado_noticia_id AS id FROM clipping_itens WHERE fonte_chave = %s AND "
                           "importado_noticia_id IS NOT NULL", (FONTE_VERIFICACAO,), fetch=True):
        db._rodar("DELETE FROM noticias WHERE id = %s", (linha["id"],), commit=True)
    db._rodar("DELETE FROM clipping_itens WHERE fonte_chave = %s", (FONTE_VERIFICACAO,), commit=True)
    db._rodar("DELETE FROM clipping_historico WHERE nome = %s", ("Verificação do seed",), commit=True)
    db._rodar("DELETE FROM autores WHERE nome = %s", (clipping_mod.PREFIXO_AUTOR + NOME_FONTE_VERIFICACAO,), commit=True)
    db._rodar("DELETE FROM tempo_cache WHERE chave = %s", (tempo_mod.chave_cache(LOCAL_VERIFICACAO),), commit=True)
    for feed in ("https://exemplo.invalid/rss.xml", "https://exemplo.invalid/atom.xml", "https://exemplo.invalid/fora.xml"):
        db._rodar("DELETE FROM clipping_feeds_estado WHERE chave = %s", (clipping_mod.chave_url(feed),), commit=True)


class _RedeSimulada:
    """buscar() de mentira: devolve as fixtures; nada sai para a internet."""
    def __init__(self):
        from app.rede import ErroRede, RespostaHttp
        self.ErroRede, self.Resposta = ErroRede, RespostaHttp
        self.chamadas = []

    def __call__(self, url, params=None, timeout=10, cabecalhos=None, max_bytes=0):
        self.chamadas.append(url)
        if "open-meteo" in url:
            return self.Resposta(200, _ler_fixture("open_meteo_santa_maria.json"))
        if url.endswith("rss.xml"):
            return self.Resposta(200, _ler_fixture("rss_exemplo.xml"))
        if url.endswith("atom.xml"):
            return self.Resposta(200, _ler_fixture("atom_exemplo.xml"))
        if url.endswith("fora.xml"):
            raise self.ErroRede("O servidor demorou demais para responder (tempo esgotado).")
        return self.Resposta(404)


def verificar_tempo_e_clipping(v, db, logger):
    """Confere, sem internet, as tabelas novas, o parser, o cache do tempo, a importação e as falhas parciais.
    Tudo o que cria é removido no fim."""
    print("\nPrevisão do tempo e Clipping (offline, com tests/fixtures)")
    if not FIXTURES.is_dir():
        v.avisar("pasta tests/fixtures ausente: verificação do clipping/tempo ignorada")
        return
    for tabela in ("tempo_cache", "clipping_itens", "importacoes_salvas", "clipping_historico",
                   "clipping_feeds_estado", "clipping_feeds_proprios"):
        try:
            db._rodar(f"SELECT 1 FROM {tabela} LIMIT 1", fetch=True)
            v.checar(f"tabela {tabela} existe (migração automática)", True)
        except ErroBanco as e:
            v.checar(f"tabela {tabela} existe (migração automática)", False, str(e))
    try:
        db._rodar("SELECT fonte_nome, fonte_url, fonte_guid FROM noticias LIMIT 1", fetch=True)
        v.checar("colunas fonte_nome/fonte_url/fonte_guid em noticias", True)
    except ErroBanco as e:
        v.checar("colunas fonte_nome/fonte_url/fonte_guid em noticias", False, str(e))
        return

    rede_falsa = _RedeSimulada()
    _limpar_clipping_seed(db)
    try:
        # ---- tempo ----
        servico = tempo_mod.TempoService(db, logger)
        r = servico.obter_previsao(LOCAL_VERIFICACAO, forcar=True, buscar=rede_falsa)
        v.checar("previsão lida da fixture do Open-Meteo", r.ok and r.dados["atual"]["descricao"] == "Poucas nuvens",
                 r.mensagem)
        v.checar("previsão traz 24 horas e 7 dias", r.ok and len(r.dados["horas"]) == 24 and len(r.dados["dias"]) == 7)
        v.checar("alerta de UV gerado pela regra", r.ok and any("UV" in a for a in tempo_mod.gerar_alertas(r.dados)))
        antes = len(rede_falsa.chamadas)
        r2 = servico.obter_previsao(LOCAL_VERIFICACAO, buscar=rede_falsa)
        v.checar("segunda leitura vem do cache (sem rede)", r2.ok and r2.dados["origem"] == "cache"
                 and len(rede_falsa.chamadas) == antes)

        def sem_rede(*a, **k):
            raise rede_falsa.ErroRede("Sem conexão com a internet.")
        r3 = servico.obter_previsao(LOCAL_VERIFICACAO, forcar=True, buscar=sem_rede)
        v.checar("sem internet: usa o cache e marca como desatualizado", r3.ok and r3.dados["desatualizada"])
        v.checar("códigos WMO em português", tempo_mod.descrever_codigo(95)[0] == "Tempestade"
                 and tempo_mod.descrever_codigo(63)[0] == "Chuva")

        # ---- clipping ----
        catalogo = [{"chave": FONTE_VERIFICACAO, "nome": NOME_FONTE_VERIFICACAO, "ativo": True, "proprio": False,
                     "feeds": [{"secao": "Política", "url": "https://exemplo.invalid/rss.xml", "categoria_sugerida": "politica",
                                "chave_feed": FONTE_VERIFICACAO + ":politica", "verificacao": "indireta"},
                               {"secao": "Geral", "url": "https://exemplo.invalid/atom.xml", "categoria_sugerida": None,
                                "chave_feed": FONTE_VERIFICACAO + ":geral", "verificacao": "indireta"},
                               {"secao": "Fora do ar", "url": "https://exemplo.invalid/fora.xml", "categoria_sugerida": None,
                                "chave_feed": FONTE_VERIFICACAO + ":fora", "verificacao": "indireta"}]}]
        cs = clipping_mod.ClippingService(db, logger, gerenciador_midia, catalogo=catalogo)
        filtro = clipping_mod.FiltroClipping(fontes=[FONTE_VERIFICACAO], periodo_horas=24 * 365 * 5, limite_por_fonte=50,
                                             ocultar_importados=False)
        previa = cs.buscar_agora(0, filtro, rede_falsa)
        itens = previa.dados["itens"] if previa.ok else []
        v.checar("prévia lê RSS e Atom das fixtures (acentos, HTML limpo)",
                 previa.ok and len(itens) == 6 and all("<" not in (i.get("resumo") or "") for i in itens), previa.mensagem)
        v.checar("feed fora do ar não derruba os outros (motivo informado)",
                 previa.ok and len(previa.dados["falhas"]) == 1 and "tempo esgotado" in previa.dados["falhas"][0]["motivo"])
        selecionados = [i for i in itens if "Gre-Nal" in i["titulo"] or "Economia cresce" in i["titulo"]]
        res = cs.importar(0, selecionados, nome="Verificação do seed")
        v.checar("importação cria matérias", res.ok and res.dados["importadas"] == 2, res.mensagem)
        criadas = db._rodar("SELECT status, conteudo, fonte_nome, fonte_url, imagem FROM noticias WHERE fonte_nome = %s",
                            (NOME_FONTE_VERIFICACAO,), fetch=True)
        v.checar("matérias importadas ficam em_pauta, nunca publicadas", len(criadas) == 2
                 and all(c["status"] == "em_pauta" for c in criadas))
        v.checar("atribuição no texto e nos campos da fonte", all(
            f"Fonte: [{NOME_FONTE_VERIFICACAO}](" in c["conteudo"] and c["fonte_url"].startswith("http") for c in criadas))
        v.checar("nenhuma imagem baixada", all(c["imagem"] is None for c in criadas))
        again = cs.importar(0, selecionados, nome="Verificação do seed")
        v.checar("reimportar não duplica", again.dados["importadas"] == 0 and again.dados["existentes"] == 2)
        marcados = cs.previa(0, filtro)
        v.checar("itens importados aparecem marcados na prévia", marcados.ok and sum(
            1 for i in marcados.dados["itens"] if i["ja_importado"]) == 2)
        v.checar("publicar direto é recusado", not cs.importar(0, selecionados, status_destino="publicado").ok)
    finally:
        _limpar_clipping_seed(db)
    sobras = db._rodar("SELECT COUNT(*) AS n FROM noticias WHERE fonte_nome = %s", (NOME_FONTE_VERIFICACAO,), fetch=True)
    v.checar("dados temporários do clipping removidos", sobras[0]["n"] == 0)


# ---------------------------------------------------------------------------
# Verificação de rede (opcional): roda NA MÁQUINA DO USUÁRIO
# ---------------------------------------------------------------------------
def verificar_rede(com_ip=False):
    """python seed.py --verificar-rede: testa ao vivo cada feed do catálogo e a API do tempo (OK/FALHA).
    Não usa banco. Uma requisição por feed (respeita o intervalo mínimo por ser uma única coleta)."""
    from app import rede
    print("Verificação ao vivo (precisa de internet; em rede de faculdade/empresa pode exigir proxy)\n")
    falhas = 0
    print("Feeds do catálogo (config/fontes_noticias.json)")
    feeds = []
    for fonte in clipping_mod.carregar_catalogo():
        if not fonte["feeds"]:
            print(f"  ----   {fonte['nome']}: sem feed cadastrado (use 'Adicionar feed próprio' na tela Clipping)")
        for feed in fonte["feeds"]:
            feeds.append({"fonte_chave": fonte["chave"], "fonte_nome": fonte["nome"], "secao": feed["secao"],
                          "url": feed["url"], "verificacao": feed["verificacao"]})
    for r in clipping_mod.coletar_feeds(feeds, {}, rede.buscar, datetime.now(), pausa=1.0):
        f = r["feed"]
        ok = r["status"] in ("ok", "nao_modificado")
        falhas += 0 if ok else 1
        marca = "OK    " if ok else "FALHA "
        print(f"  {marca} {f['fonte_nome']} — {f['secao']}: {r['motivo']}  [{f['verificacao']}]")
    print("\nPrevisão do tempo (Open-Meteo)")
    local = tempo_mod.CIDADE_PADRAO
    try:
        previsao = tempo_mod.interpretar_previsao(tempo_mod.baixar_previsao(local))
        a = previsao["atual"]
        print(f"  OK     previsão de {local['nome']}: {a['temperatura']}°C, {a['descricao']}; "
              f"{len(previsao['horas'])} horas e {len(previsao['dias'])} dias")
    except Exception as e:
        falhas += 1
        print(f"  FALHA  previsão: {e}")
    try:
        cidades = tempo_mod.buscar_cidades_rede(local["nome"])
        print(f"  OK     busca de cidades: {len(cidades)} resultado(s) para '{local['nome']}'")
    except Exception as e:
        falhas += 1
        print(f"  FALHA  busca de cidades: {e}")
    if com_ip:
        try:
            achada = tempo_mod.localizar_por_ip_rede()
            print(f"  OK     localização por IP: {tempo_mod.rotulo_local(achada)}")
        except Exception as e:
            falhas += 1
            print(f"  FALHA  localização por IP: {e}")
    else:
        print("  ----   localização por IP não testada (envia seu IP a um terceiro); use --com-ip para testar")
    print(f"\n{'Tudo certo.' if not falhas else str(falhas) + ' falha(s). Veja README > Solução de problemas de rede.'}")
    return falhas


# ---------------------------------------------------------------------------
# Conexão (com ajuda para os erros mais comuns)
# ---------------------------------------------------------------------------
def preparar_banco(host, usuario, senha, banco):
    """Cria o banco e as tabelas a partir de sql/schema.sql se o banco ainda não existir."""
    import mysql.connector
    schema = RAIZ / "sql" / "schema.sql"
    if not schema.is_file():
        print("  sql/schema.sql não encontrado.")
        return False
    try:
        conexao = mysql.connector.connect(host=host, user=usuario, password=senha)
        cursor = conexao.cursor()
        sql = re.sub(r"--[^\n]*", "", schema.read_text(encoding="utf-8"))
        sql = re.sub(r"(CREATE DATABASE IF NOT EXISTS|USE)\s+newsmanager", rf"\1 {banco}", sql)
        for comando in (c.strip() for c in sql.split(";")):
            if comando:
                cursor.execute(comando)
        conexao.commit()
        conexao.close()
        return True
    except mysql.connector.Error as erro:
        explicar_erro_mysql(erro, host)
        return False


def explicar_erro_mysql(erro, host="localhost"):
    codigo = getattr(erro, "errno", None)
    print(f"\nNão foi possível usar o MySQL ({erro}).")
    if codigo == 2003:
        print("-> O servidor MySQL não está rodando em", host + ". No Windows, abra o PowerShell como administrador e rode:\n"
              "   net start MySQL80\n   (ou veja a opção sem administrador no passo a passo que combinamos).")
    elif codigo == 1045:
        print("-> Usuário ou senha incorretos. Use --usuario e --senha, ou ajuste o main.py.")
    elif codigo == 1049:
        print("-> O banco ainda não existe. Rode sql/schema.sql ou deixe o seed criá-lo.")
    else:
        print("-> Confira host, usuário, senha e se o MySQL está ativo.")


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError):
        pass
    ap = argparse.ArgumentParser(description="Dados de teste e verificação do NewsManager.")
    ap.add_argument("--verificar", action="store_true", help="só roda as verificações")
    ap.add_argument("--limpar", action="store_true", help="remove os dados criados pelo seed")
    ap.add_argument("--recriar", action="store_true", help="limpar + popular + verificar")
    ap.add_argument("--autosave", action="store_true", help="cria um auto-salvamento de exemplo para o editor")
    ap.add_argument("--sem-imagens", action="store_true", help="não gera capas nem fotos")
    ap.add_argument("--volume", type=int, default=120, help="matérias extras para os gráficos (padrão 120; 0 = nenhuma)")
    ap.add_argument("--verificar-rede", action="store_true",
                    help="testa AO VIVO os feeds do clipping e a API do tempo (precisa de internet; não usa o banco)")
    ap.add_argument("--com-ip", action="store_true", help="com --verificar-rede, testa também a localização por IP")
    ap.add_argument("--host", default="localhost")
    ap.add_argument("--usuario", default="root")
    ap.add_argument("--senha", default="")
    ap.add_argument("--banco", default="newsmanager")
    args = ap.parse_args()

    if args.verificar_rede:
        sys.exit(1 if verificar_rede(args.com_ip) else 0)

    logger = Logger()
    db = DatabaseManager(host=args.host, user=args.usuario, password=args.senha, database=args.banco)
    if not db.conectar():
        print("Banco indisponível. Tentando preparar o banco a partir de sql/schema.sql...")
        if not (preparar_banco(args.host, args.usuario, args.senha, args.banco) and db.conectar()):
            print("\nNão foi possível conectar. Resolva o erro acima e rode o seed de novo.")
            sys.exit(2)
        print("Banco criado a partir de sql/schema.sql.\n")

    falhou = False
    try:
        if args.limpar:
            limpar(db, logger)
        elif args.verificar:
            falhou = bool(verificar(db, logger).falhas)
        else:
            if args.recriar:
                limpar(db, logger)
                print()
            popular(db, logger, com_imagens=not args.sem_imagens, autosave=args.autosave, volume=max(0, args.volume))
            falhou = bool(verificar(db, logger).falhas)
    finally:
        db.desconectar()
    sys.exit(1 if falhou else 0)


if __name__ == "__main__":
    main()
