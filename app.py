"""Standalone interface for the NBR 14762:2010 simply supported member calculator."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import re
import sys

import streamlit as st

_APP_DIRECTORY = Path(__file__).resolve().parent
if not (_APP_DIRECTORY / "tercas").is_dir():
    _RUNTIME_ARCHIVE = _APP_DIRECTORY / "tercas_runtime.zip"
    if _RUNTIME_ARCHIVE.is_file():
        if str(_RUNTIME_ARCHIVE) not in sys.path:
            sys.path.insert(0, str(_RUNTIME_ARCHIVE))
    else:
        st.error(
            "O pacote de cálculo não foi enviado. Coloque tercas_runtime.zip ao lado de app.py "
            "usando o pacote de publicação simples, ou envie a pasta tercas inteira do pacote completo. "
            "Não extraia o arquivo tercas_runtime.zip."
        )
        st.stop()

from tercas import engine, sections
from tercas import catalog
from tercas.presets import PRESETS
from tercas.project import default_project, import_project_json, project_fingerprint, validate_project
from tercas.reports import project_json, report_html, report_json
from tercas.visuals import diagram_figure, member_figure, number, section_figure, utilization_figure

st.set_page_config(page_title="Terças | NBR 14762", page_icon=":material/architecture:", layout="wide")

STATUS = {
    "pass": "Calculado · atende",
    "fail": "Reprovado",
    "pending": "Pendente",
    "not_applicable": "Não aplicável",
    "excluded": "Excluída por opção de projeto",
    "partial": "Parcial — escopo adotado",
}
RESTRAINTS = {
    "continuous": "Contenção contínua",
    "none": "Sem contenção intermediária",
    "discrete": "Contenções discretas",
    "panel": "Painel conectado à mesa",
}
PLOT_CONFIG = {"displaylogo": False, "scrollZoom": False}

if "project" not in st.session_state:
    st.session_state.project = default_project()
    st.session_state.revision = 0
    st.session_state.result = None
    st.session_state.result_fingerprint = None
elif st.session_state.project.get("schema_version") in (1, 2, 3, 4):
    st.session_state.project = validate_project(st.session_state.project)
    st.session_state.revision += 1
    st.session_state.result = None
    st.session_state.result_fingerprint = None


def widget_key(path: str) -> str:
    return f"input_{st.session_state.revision}_{path}"


def replace_project(value: dict) -> None:
    st.session_state.project = deepcopy(value)
    st.session_state.revision += 1
    st.session_state.result = None
    st.session_state.result_fingerprint = None


def select_catalog_profile(key: str, identifier: str | None = None) -> None:
    identifier = identifier if identifier is not None else st.session_state[key]
    if identifier is None:
        st.session_state.result = None
        st.session_state.result_fingerprint = None
        return
    entry = catalog.entry_by_id(identifier)
    value = deepcopy(st.session_state.project)
    changed = value['profile'] != entry['profile']
    value['profile'] = deepcopy(entry['profile'])
    value['material']['nu'] = 0.3
    value['member']['minor_critical_mode'] = 'automatic'
    for field in ('ml_minor_pos_kNm', 'ml_minor_neg_kNm', 'mdist_minor_pos_kNm',
                  'mdist_minor_neg_kNm', 'mdist_major_kNm', 'mdist_minor_kNm'):
        value['member'][field] = None
    value['member']['minor_critical_source'] = ''
    if changed:
        value['member']['ndist_kN'] = None
        value['tension'] = dict.fromkeys(('an0_mm2', 'an_mm2', 'ct'), None)
    replace_project(value)


def numeric(target: dict, field: str, label: str, group: str, *, minimum: float | None = 0.0,
            maximum: float | None = None, step: float = 1.0, digits: int = 2,
            help_text: str | None = None, optional: bool = False) -> None:
    value = target[field]
    key = widget_key(f"{group}_{field}")
    initial = None if value is None else float(value)
    if optional:
        # Keep a genuinely empty default so clearing a previously supplied
        # eigenvalue returns None instead of silently restoring its old value.
        if key not in st.session_state:
            st.session_state[key] = initial
        initial = None
    target[field] = st.number_input(
        label, min_value=minimum, max_value=maximum,
        value=initial, step=float(step), format=f"%.{digits}f",
        key=key, help=help_text,
        placeholder="Não informado" if optional else None,
        persist_state="session",
    )


def boolean(target: dict, field: str, label: str, group: str, help_text: str | None = None) -> None:
    target[field] = st.checkbox(label, value=bool(target[field]), key=widget_key(f"{group}_{field}"),
                                help=help_text, persist_state="session")


def table(rows: list[dict], name: str) -> None:
    if rows:
        st.dataframe(rows, hide_index=True, width="stretch", alt=name)
    else:
        st.caption("Nenhum registro para esta seleção.")


@st.cache_data(max_entries=12, show_spinner=False, scope="session")
def calculate_cached(value: dict) -> dict:
    return engine.calculate(value)


@st.cache_data(max_entries=4, show_spinner=False, scope="session")
def html_cached(value: dict) -> str:
    return report_html(value)


with st.sidebar:
    st.subheader("Seu caso", icon=":material/folder_open:")
    st.caption("Entradas e resultados ficam nesta sessão. Baixe o projeto para retomá-lo depois.")
    selected_preset = st.selectbox("Exemplo do caderno", list(PRESETS), key="preset_selection")
    if st.button("Carregar exemplo", icon=":material/book:", width="stretch", key="load_preset"):
        replace_project(PRESETS[selected_preset])
        st.rerun()
    if st.button("Novo projeto", icon=":material/add:", width="stretch", key="new_project"):
        replace_project(default_project())
        st.rerun()
    with st.expander("Abrir projeto JSON", icon=":material/upload_file:"):
        uploaded = st.file_uploader("Arquivo de entradas", type=["json"], key="project_upload")
        if st.button("Importar entradas", disabled=uploaded is None, key="import_project") and uploaded is not None:
            try:
                loaded = import_project_json(uploaded.getvalue().decode("utf-8-sig"))
            except (ValueError, UnicodeDecodeError) as exc:
                st.error(str(exc))
            else:
                replace_project(loaded)
                st.rerun()
    project_download = st.container()
    st.divider()
    st.caption("NBR 14762:2010 · perfis U e Ue · barra biapoiada")
    st.caption("A avaliação do galpão, das contenções e das ligações deve ser compatível com as hipóteses informadas.")

draft = deepcopy(st.session_state.project)
profile, material, member = draft["profile"], draft["material"], draft["member"]
loads, support, panel, limits = draft["loads"], draft["support"], draft["panel"], draft["limits"]
tension = draft.setdefault("tension", {"an0_mm2": None, "an_mm2": None, "ct": None})

st.title("Terças de aço formadas a frio")
st.caption("Da seção à memória de cálculo · NBR 14762:2010")
draft["name"] = st.text_input("Identificação do caso", value=draft["name"], max_chars=160,
                               key=widget_key("name"), placeholder="Ex.: cobertura — eixo 3")
tab_section, tab_loads, tab_restraints, tab_results = st.tabs(
    ["1 · Seção e vão", "2 · Ações", "3 · Vínculos e contenções", "4 · Resultados"]
)

props = None
catalog_entries = catalog.entries()
catalog_labels = {entry['id']: entry['label'] for entry in catalog_entries}
current_catalog = catalog.match_profile(profile)
catalog_ready = current_catalog is not None and abs(material['nu'] - 0.3) < 1e-12
with tab_section:
    input_column, drawing_column = st.columns([1.05, 1.25], gap="large")
    with input_column:
        with st.container(border=True):
            st.subheader("Seção transversal")
            ids = list(catalog_labels)
            selection_key = widget_key('catalog_profile')
            selected_catalog_id = st.selectbox('Perfil com dados cadastrados', ids,
                         index=ids.index(current_catalog['id']) if current_catalog is not None else None,
                         format_func=lambda identifier: catalog_labels[identifier],
                         placeholder='Selecione um perfil do catálogo',
                         key=selection_key, on_change=select_catalog_profile, args=(selection_key,), required=True,
                         help='A seleção carrega dimensões, raio, ν = 0,30 e críticos do catálogo, sem interpolação. Ao trocar de seção, informe novamente as áreas líquidas e Ct da ligação, se houver tração.')
            if current_catalog is None:
                st.warning('O perfil deste projeto não consta do catálogo. As entradas foram preservadas; selecione um perfil cadastrado para calcular nesta interface.')
            else:
                st.caption(f"{profile['family']} · h = {number(profile['h_mm'])} mm · b = {number(profile['b_mm'])} mm · "
                           f"D = {number(profile['d_mm'])} mm · t = {number(profile['t_mm'])} mm · ri = {number(profile['r_mm'])} mm")
                st.caption('Dimensões externas e espessura do aço base. O raio cadastrado precisa corresponder ao perfil utilizado na obra.')
                st.caption('Críticos de flexão pré-calculados e documentados. Os dados não são uma certificação de fabricante nem uma transcrição do DimPerfil.')
        with st.container(border=True):
            st.subheader("Vão e inclinação")
            c1, c2 = st.columns(2)
            with c1:
                numeric(member, "L_m", "Vão biapoiado L (m)", "member", minimum=0.1, maximum=100.0, step=0.5)
            with c2:
                numeric(member, "angle_deg", "Inclinação da cobertura (°)", "member", minimum=-89.0,
                        maximum=89.0, step=1.0)
        with st.expander("Aço e propriedades elásticas", expanded=False):
            c1, c2 = st.columns(2)
            with c1:
                numeric(material, "fy_mpa", "Escoamento fy (MPa)", "material", minimum=1.0, step=10.0, digits=0)
                numeric(material, "E_mpa", "Módulo E (MPa)", "material", minimum=1.0, step=1000.0, digits=0)
                st.caption(f"Coeficiente de Poisson do projeto: ν = {number(material['nu'], 2)}. Catálogo calculado com ν = 0,30.")
                if not catalog_ready and current_catalog is not None:
                    st.warning('O ν importado difere da base do catálogo. Aplique novamente o perfil para usar ν = 0,30.')
                    if st.button('Aplicar base elástica do catálogo', key='apply_catalog_material'):
                        select_catalog_profile(selection_key, current_catalog['id'])
                        st.rerun()
            with c2:
                numeric(material, "fu_mpa", "Ruptura fu (MPa)", "material", minimum=1.0, step=10.0, digits=0)
                numeric(material, "G_mpa", "Módulo G (MPa)", "material", minimum=1.0, step=1000.0, digits=0)
                numeric(material, "density_kgm3", "Massa específica (kg/m³)", "material", minimum=1.0,
                        step=50.0, digits=0)
    with drawing_column:
        with st.container(border=True):
            st.subheader("Geometria e eixos locais")
            try:
                props = sections.section_properties(profile, material)
            except ValueError as exc:
                st.warning(str(exc), title="Confira a geometria")
            if props is not None:
                st.plotly_chart(section_figure(profile, props), config={**PLOT_CONFIG, "displayModeBar": False},
                                key="section_drawing", alt="Seção com altura, mesas, enrijecedores e eixos locais x e y")
                st.caption("CG: centro de gravidade · CT: centro de torção. Traço da espessura ampliado para leitura; cotas em mm.")
                c1, c2 = st.columns(2)
                c1.metric("Área bruta", f"{number(props['A'] / 100, 3)} cm²")
                c2.metric("Massa linear", f"{number(props['mass'], 3)} kg/m")
                c1.metric("Inércia Ix", f"{number(props['Ix'] / 10000, 2)} cm⁴")
                c2.metric("Inércia Iy", f"{number(props['Iy'] / 10000, 2)} cm⁴")
                st.caption(f"Peso próprio calculado: {number(props['pp'], 6)} kN/m.")
        st.info("Mx solicita o eixo de maior inércia. My positivo comprime as bordas livres das mesas; a abertura do perfil segue o desenho.",
                icon=":material/straighten:")
        with st.expander("Propriedades completas"):
            if props:
                properties = [("A", "Área bruta", "mm²"), ("Ix", "Inércia x", "mm⁴"),
                              ("Iy", "Inércia y", "mm⁴"), ("Wx", "Módulo elástico x", "mm³"),
                              ("xc", "CG a partir da linha média da alma", "mm"),
                              ("xsc", "CT em relação ao CG", "mm"), ("rx", "Raio de giração x", "mm"),
                              ("ry", "Raio de giração y", "mm"), ("J", "Constante de torção", "mm⁴"),
                              ("Cw", "Constante de empenamento", "mm⁶")]
                table([{"Grandeza": label, "Valor": number(props.get(key)), "Unidade": unit}
                       for key, label, unit in properties], "Propriedades geométricas da seção")
                st.caption("J, Cw e CT usam a aproximação de parede delgada documentada na memória.")

with tab_loads:
    loads["mode"] = st.segmented_control(
        "Como informar as ações?", ["characteristic", "design"],
        format_func=lambda value: "Cargas características" if value == "characteristic" else "Cargas já combinadas",
        default=loads["mode"], required=True, key=widget_key("load_mode"),
    )
    if loads["mode"] == "characteristic":
        st.info("Informe cargas lineares características. O peso próprio do perfil é acrescentado automaticamente; pressão e sucção são casos alternativos.")
        left, right = st.columns(2, gap="large")
        with left, st.container(border=True):
            st.subheader("Gravidade")
            numeric(loads, "g_metal_kNm", "Permanentes metálicas adicionais (kN/m)", "loads", step=0.01, digits=6,
                    help_text="Exclua o peso próprio do perfil, calculado pela geometria. Inclua apenas os demais componentes metálicos.")
            numeric(loads, "g_roof_kNm", "Telha e componentes industrializados (kN/m)", "loads", step=0.05, digits=3)
            numeric(loads, "q_kNm", "Ação variável distribuída Q (kN/m)", "loads", step=0.05, digits=3)
            st.caption("A gravidade é vertical e será decomposta conforme a inclinação da cobertura.")
        with right, st.container(border=True):
            st.subheader("Vento normal à cobertura")
            numeric(loads, "wind_down_kNm", "Pressão — para baixo (kN/m)", "loads", step=0.05, digits=3)
            numeric(loads, "wind_up_kNm", "Sucção — para cima (kN/m)", "loads", step=0.05, digits=3)
            st.caption("Use magnitudes positivas já convertidas pela faixa tributária. O cálculo das pressões de vento não faz parte deste app.")
        with st.expander("Força de manutenção e coeficientes de combinação"):
            c1, c2 = st.columns(2)
            with c1:
                numeric(loads, "point_kN", "Força de manutenção característica (kN)", "loads", step=0.1, digits=3)
            with c2:
                numeric(loads, "point_x_m", "Posição a partir do apoio esquerdo (m)", "loads", step=0.1, digits=3)
            st.caption("A força pontual é alternativa a Q distribuída. A introdução local da força no vão permanece uma verificação separada.")
            for action, suffix in [("Variável gravitacional Q", "q"), ("Vento W", "w")]:
                st.markdown(f"**{action}**")
                for column, index in zip(st.columns(3), range(3)):
                    with column:
                        numeric(loads, f"psi{index}_{suffix}", f"ψ{index} — {suffix.upper()}", "loads", maximum=1.0, step=0.05)
            st.caption("Valores iniciais de Q para cobertura: ψ0 = 0,8; ψ1 = 0,7; ψ2 = 0,6. Confira a categoria da ação. ELS rara usa ψ1 para ações acompanhantes na edição 2010.")
    else:
        st.info("Os valores abaixo já são totais e concomitantes de cada combinação. Não há nova majoração, decomposição pela inclinação ou adição de peso próprio.")
        left, right = st.columns(2, gap="large")
        for column, title, prefix, nkey in [(left, "Estado-limite último", "qd", "nsd_kN"),
                                            (right, "Estado-limite de serviço", "qs", "nser_kN")]:
            with column, st.container(border=True):
                st.subheader(title)
                numeric(loads, f"{prefix}_normal_kNm", "Carga normal / direção y (kN/m)", "loads",
                        minimum=None, step=0.05, digits=3)
                numeric(loads, f"{prefix}_parallel_kNm", "Carga paralela / direção x (kN/m)", "loads",
                        minimum=None, step=0.05, digits=3)
                numeric(loads, nkey, "Força axial (kN)", "loads", minimum=None, step=1.0, digits=3)
        st.caption("Normal positiva: gravidade. Normal negativa: sucção. My positivo comprime bordas livres. N positivo: compressão; N negativo: tração.")
        st.warning("A análise com força axial representa uma barra ideal isolada, inicialmente reta. Ela não substitui a análise global do galpão nem a consideração das imperfeições do sistema.")
        with st.expander("Dados para resistência à tração"):
            st.caption("Informe valores obtidos pelo detalhamento real e pelo item 9.6. Sem essas entradas, a resistência final à tração permanece pendente.")
            c1, c2, c3 = st.columns(3)
            with c1:
                numeric(tension, "an0_mm2", "Área líquida fora da ligação An0 (mm²)", "tension",
                        minimum=0.001, digits=3, optional=True)
            with c2:
                numeric(tension, "an_mm2", "Área líquida na ligação An (mm²)", "tension",
                        minimum=0.001, digits=3, optional=True,
                        help_text="Área líquida calculada conforme 9.6, incluindo a redução normativa aplicável. Não informe apenas a área bruta.")
            with c3:
                numeric(tension, "ct", "Eficiência da ligação Ct", "tension", minimum=0.001,
                        maximum=1.0, step=0.01, digits=4, optional=True)
            st.caption("Ct deve ser calculado para a forma de conexão adotada. Esses dados não dimensionam a ligação nem verificam efeitos fora do seu plano.")
    with st.expander("Conversor auxiliar: carga por área → carga linear"):
        c1, c2 = st.columns(2)
        surface = c1.number_input("Carga por área (kN/m²)", min_value=0.0, value=0.5, step=0.05, key="surface_load")
        tributary = c2.number_input("Faixa tributária (m)", min_value=0.0, value=1.5, step=0.1, key="tributary_width")
        st.metric("Carga linear correspondente", f"{number(surface * tributary, 4)} kN/m")
        st.caption("Transfira esse valor ao campo pertinente. O conversor não acrescenta cargas ao projeto.")

with tab_restraints:
    st.subheader("Estabilidade e condições de apoio")
    member["restraint"] = st.segmented_control(
        "Contenção lateral da barra", list(RESTRAINTS), format_func=lambda value: RESTRAINTS[value],
        default=member["restraint"], required=True, key=widget_key("restraint"), width="stretch",
    )
    if member["restraint"] == "discrete":
        numeric(member, "Lb_m", "Distância entre contenções laterais E torcionais (m)", "member",
                minimum=0.01, step=0.25,
                help_text="A contenção precisa impedir as duas formas de movimento admitidas no modelo.")
        st.info("Lb altera a estabilidade; o vão principal da flexão e da flecha continua sendo L. Um tirante isolado não comprova automaticamente contenção à torção.")
    else:
        if member["Lb_m"] > member["L_m"]:
            member["Lb_m"] = member["L_m"]
        if member["restraint"] == "continuous":
            st.caption("Hipótese: contenção contínua eficaz da mesa comprimida para cada sentido de carregamento analisado. A ligação e sua rigidez precisam justificar essa condição.")
        elif member["restraint"] == "none":
            st.caption("A barra possui somente as contenções nas extremidades; o comprimento de estabilidade é o vão principal.")
    st.plotly_chart(member_figure(draft), config={**PLOT_CONFIG, "displayModeBar": False},
                    key="member_drawing", alt="Barra biapoiada com o vão principal e posições das contenções")
    c1, c2 = st.columns(2)
    with c1:
        boolean(member, "end_fork", "Extremidades com vínculo de garfo", "member",
                "Deslocamento lateral das duas mesas e torção impedidos nas extremidades.")
        boolean(member, "warping_free", "Empenamento livre nos apoios", "member")
    with c2:
        boolean(member, "load_at_shear_center", "Resultante transversal passa pelo centro de torção", "member",
                "Uma excentricidade de aplicação pode gerar torção não coberta pelo modelo de flexão.")
    if member["restraint"] == "panel":
        with st.container(border=True):
            st.subheader("Painel e fixação — Anexo F")
            st.caption("Para gravidade, a mesa conectada é considerada contida. Para sucção, a mesa tracionada fica ligada ao painel e o Anexo F só pode ser aplicado dentro de seu domínio.")
            c1, c2, c3 = st.columns(3)
            with c1:
                numeric(panel, "thickness_mm", "Espessura da telha de aço (mm)", "panel", minimum=0.01, step=0.05)
                numeric(panel, "rib_height_mm", "Altura das nervuras (mm)", "panel")
            with c2:
                numeric(panel, "rib_pitch_mm", "Passo das nervuras (mm)", "panel", minimum=1.0, step=10.0)
                numeric(panel, "fastener_pitch_mm", "Passo dos conectores (mm)", "panel", minimum=1.0, step=10.0)
            with c3:
                numeric(panel, "fastener_mm", "Diâmetro do parafuso (mm)", "panel", minimum=0.1, step=0.1)
                numeric(panel, "washer_mm", "Diâmetro da arruela (mm)", "panel", minimum=0.1, step=0.5)
            boolean(panel, "near_center", "Conectores próximos ao centro da mesa", "panel")
            boolean(panel, "proven_stiffness", "Rigidez e fixação comprovadas para impedir movimento relativo", "panel")
            st.markdown("**Condições para usar os fatores do Anexo F:** U enrijecido; h ≤ 292 mm; 60 ≤ h/t ≤ 170; 2,8 ≤ h/b ≤ 4,5; 16 ≤ bplana/t ≤ 43; L < 10 m; fy ≤ 410 MPa. Ambas as mesas devem estar contidas lateralmente nos apoios.")
            st.markdown("**Painel de aço e conectores:** espessura ≥ 0,45 mm; nervuras ≥ 25 mm, com passo ≤ 300 mm; parafusos autoatarraxantes padronizados de no mínimo 5,5 mm, arruelas de 12,5 mm e passo de fixação ≤ 300 mm. O carregamento considerado deve estar em plano paralelo à alma.")
            st.caption("Os números preenchidos não comprovam a rigidez do conjunto ou o detalhamento da ligação. Condições fora do domínio aparecem como pendências no cálculo.")
    with st.expander("Resistência localizada nos apoios", expanded=True):
        boolean(support, "check", "Verificar força concentrada na alma junto aos apoios", "support")
        if support["check"]:
            c1, c2 = st.columns(2)
            with c1:
                numeric(support, "c_mm", "Comprimento de contato c (mm)", "support", minimum=0.1, step=10.0)
            with c2:
                numeric(support, "theta_deg", "Ângulo alma–superfície de apoio (°)", "support", minimum=1.0, maximum=90.0)
            boolean(support, "fastened", "Mesa conectada ao apoio com restrição à rotação", "support")
            st.caption("Modelo de extremidade, uma mesa carregada, alma perpendicular ao apoio (θ = 90°). A verificação da alma não dimensiona os parafusos nem a chapa de apoio.")
    with st.expander('Escopo adotado para o eixo menor e as flechas', expanded=True):
        if profile['family']=='Ue':
            boolean(member, 'exclude_minor_distortion', 'Desconsiderar distorção no eixo menor (My+ e My−)', 'member')
            if member['exclude_minor_distortion']:
                st.caption('Exclusão expressa de projeto: a resistência e a rigidez de My usam os ramos global e local. A memória não apresenta essa escolha como dispensa normativa.')
        boolean(member, 'exclude_minor_shear', 'Desconsiderar cisalhamento no eixo menor (Vx)', 'member')
        boolean(member, 'deflection_ignore_restraints', 'Desconsiderar contenções intermediárias na avaliação das flechas', 'member')
        if member['deflection_ignore_restraints']:
            st.caption(f"Flechas pelo modelo biapoiado no vão integral de {number(member['L_m'])} m. As contenções continuam consideradas na estabilidade ELU.")
    if profile["family"] == "Ue":
        with st.expander("Flexão no eixo menor do Ue — Anexo C", expanded=True):
            member["minor_critical_mode"] = st.segmented_control(
                "Momentos críticos do eixo menor", ["automatic", "manual"],
                format_func=lambda value: {"automatic": "Usar valores do catálogo", "manual": "Informar valores externos"}[value],
                default=member["minor_critical_mode"], required=True,
                key=widget_key("member_minor_critical_mode"), persist_state="session")
            if member["minor_critical_mode"] == "automatic":
                st.caption("Os críticos locais e distorcionais de Mx e dos dois sentidos de My são lidos do catálogo para esta geometria. Você não precisa digitá-los. Se E mudar, os críticos são ajustados proporcionalmente; fy entra depois nas resistências.")
                st.info("A memória identifica o perfil, a análise de referência e a convergência. A análise considera a seção isolada, sem aproveitar restrição local ou distorcional da telha. A opção manual permanece para projetos e exemplos anteriores.")
            else:
                st.caption('O aplicativo calcula Me pelo Anexo E e usa os críticos locais do sentido solicitado. '+
                           ('O ramo distorcional está excluído por escolha de projeto.' if member['exclude_minor_distortion'] else 'O ramo distorcional também participa da resistência e da rigidez de serviço.'))
                pos_column, neg_column = st.columns(2)
                with pos_column:
                    st.markdown("**My positivo — bordas e enrijecedores comprimidos**")
                    numeric(member, "ml_minor_pos_kNm", "Mℓ,y+ local (kN·m)", "member", minimum=0.001, step=0.5, digits=3, optional=True)
                    if not member['exclude_minor_distortion']:
                        numeric(member, "mdist_minor_pos_kNm", "Mdist,y+ distorcional (kN·m)", "member", minimum=0.001, step=0.5, digits=3, optional=True)
                with neg_column:
                    st.markdown("**My negativo — lado da alma comprimido**")
                    numeric(member, "ml_minor_neg_kNm", "Mℓ,y− local (kN·m)", "member", minimum=0.001, step=0.5, digits=3, optional=True)
                    if not member['exclude_minor_distortion']:
                        numeric(member, "mdist_minor_neg_kNm", "Mdist,y− distorcional (kN·m)", "member", minimum=0.001, step=0.5, digits=3, optional=True)
                member["minor_critical_source"] = st.text_input(
                    "Origem dos momentos críticos", value=member["minor_critical_source"],
                    max_chars=500, key=widget_key("member_minor_critical_source"),
                    placeholder="Relatório, modelo e identificação dos modos e sentidos", persist_state="session")
                st.info("Preencha os dados do sentido solicitado. A dispensa distorcional da Tabela 14 vale para flexão maior; ela não é aplicada ao eixo menor. Em flexão menor pura, a flecha usa a rigidez efetiva do item C.5. Na flexão biaxial, uma seção efetiva conjunta reduzida pode exigir avaliação adicional.")
                if member["mdist_minor_kNm"] is not None:
                    st.warning(f"O projeto antigo contém Mdist,y = {number(member['mdist_minor_kNm'])} kN·m, sem sentido identificado. Esse valor foi preservado no arquivo, mas não é utilizado. Informe os valores corretos nos campos My+ e My−.")
    with st.expander("Limites de deslocamento e outros dados distorcionais"):
        st.caption("Limites na forma L/divisor. Valores mais altos são mais restritivos; confira as exigências da telha e do projeto.")
        for column, field, label in zip(st.columns(2), ["gravity_L", "uplift_L"],
                                       ["Gravidade vertical — L /", "Sucção isolada — L /"]):
            with column:
                numeric(limits, field, label, "limits", minimum=1.0, step=10.0, digits=0)
        boolean(limits, 'additional_checks', 'Aplicar também critérios adicionais de flecha normal e paralela', 'limits',
                'Desligado: somente as comparações normativas aplicáveis. O L/180 no plano da cobertura não é uma exigência universal da NBR para terças.')
        if limits['additional_checks']:
            numeric(limits, 'parallel_L', 'Paralelo — limite adicional L /', 'limits', minimum=1.0, step=10.0, digits=0)
        if member['minor_critical_mode']=='manual':
            numeric(member, 'mdist_major_kNm', 'Mdist — eixo maior (kN·m)', 'member', minimum=0.001, step=0.5, digits=3, optional=True)
        elif profile['family']=='Ue':
            st.caption('O Mdist do eixo maior é obtido do catálogo na opção automática.')
        numeric(member, 'ndist_kN', 'Ndist — compressão axial (kN)', 'member', minimum=0.001, step=0.5, digits=3, optional=True,
                help_text='O catálogo atual é de flexão. A compressão utiliza este dado externo apenas quando a dispensa normativa não é demonstrada.')

st.session_state.project = deepcopy(draft)
fingerprint = project_fingerprint(draft)
filename = re.sub(r"[^\w-]+", "_", draft["name"].strip(), flags=re.UNICODE).strip("_") or "terca"
with project_download:
    st.download_button("Salvar entradas JSON", project_json(draft), file_name=f"{filename}_entradas.json",
                       mime="application/json", icon=":material/save:", key="download_project",
                       on_click="ignore", width="stretch")

with tab_results:
    calculate_clicked = st.button("Calcular e verificar", type="primary", icon=":material/calculate:",
                                   key="calculate", width="stretch", disabled=not catalog_ready or selected_catalog_id is None)
    if calculate_clicked and catalog_ready and selected_catalog_id is not None:
        try:
            with st.spinner("Calculando estabilidade, combinações, resistências e deslocamentos…"):
                calculated = calculate_cached(draft)
        except ValueError as exc:
            st.session_state.result = None
            st.session_state.result_fingerprint = None
            st.error(str(exc), title="Revise as entradas")
        else:
            st.session_state.result = calculated
            st.session_state.result_fingerprint = fingerprint
    result = st.session_state.result
    stale = result is not None and st.session_state.result_fingerprint != fingerprint
    if result is None:
        st.info("Preencha as três primeiras áreas e calcule. O resultado apresentará os critérios atendidos, os reprovados e o que ficou pendente.")
    elif stale:
        st.warning("As entradas foram alteradas. Recalcule para atualizar tabelas, gráficos e relatórios.",
                   title="Resultado desatualizado", icon=":material/update:")
    else:
        checks = result.get("checks", [])
        pending = [check for check in checks if check.get("status") == "pending"]
        failed = [check for check in checks if check.get("status") == "fail"]
        overall = result.get("overall_status", "pending")
        if overall == "fail":
            st.error("Um ou mais critérios calculados excedem a resistência ou o limite adotado. Veja os casos governantes abaixo.", title="Há verificações reprovadas")
        elif overall == "pending":
            st.warning("Há verificações aplicáveis sem conclusão. Os itens calculados não representam atendimento completo da barra e de suas ligações.", title="Cálculo concluído com pendências")
        elif overall == 'partial':
            st.info('Os critérios calculados atendem ao escopo e às hipóteses adotadas. As condições e eventuais exclusões de projeto estão identificadas abaixo.', title='Cálculo parcial — escopo adotado')
        else:
            st.success("Os critérios implementados e aplicáveis atendem às hipóteses informadas. Consulte a cobertura e o escopo das verificações.", title="Verificações calculadas atendidas")
        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("Calculadas", sum(check.get("status") in {"pass", "fail"} for check in checks), border=True)
        c2.metric("Reprovadas", len(failed), border=True)
        c3.metric("Pendentes", len(pending), border=True)
        governing = result.get("governing") or {}
        c4.metric('Excluídas', sum(check.get('status')=='excluded' for check in checks), border=True)
        c5.metric("Utilização governante", number(governing.get("utilization")), border=True)
        if governing:
            st.caption(f"Governante: {governing.get('label', '—')} · {governing.get('case_id', '—')}")
        automatic_minor = result.get("automatic_minor", {})
        used_catalog = result.get('section_catalog')
        if used_catalog is not None:
            with st.expander('Perfil e críticos do catálogo', expanded=True):
                st.caption(f"{used_catalog['label']} · catálogo {used_catalog['catalog_version']} · E = {number(used_catalog['E_used_mpa'], 0)} MPa")
                major = used_catalog['major']
                table([{
                    'Eixo': 'Maior · Mx±',
                    'Local (kN·m)': number(major['local_Nmm']/1e6),
                    'Distorcional (kN·m)': number(major['distortional_Nmm']/1e6) if major['distortional_Nmm'] is not None else 'Não aplicável ao U simples',
                }], 'Críticos do eixo maior tabulados para o perfil selecionado')
                st.caption('O crítico local maior do catálogo é referência elástica; a resistência local maior mantém o MSE da NBR. Mdist maior alimenta a verificação distorcional quando necessária.')
        if automatic_minor.get("by_sign"):
            with st.expander("Momentos críticos calculados automaticamente", expanded=True):
                rows = []
                for sign, data in automatic_minor["by_sign"].items():
                    local, dist = data.get("local_Nmm"), data.get("distortional_Nmm")
                    rows.append({
                        "Sentido": "My+ · bordas comprimidas" if sign == "pos" else "My− · alma comprimida",
                        "Local (kN·m)": number(local / 1e6) if local is not None else "Não determinado",
                        "Distorcional (kN·m)": number(dist / 1e6) if dist is not None else
                            ("Não aplicável" if data.get("distortion_status") == "not_applicable" else "Não determinado"),
                        "Situação": "Calculado" if data.get("status") == "computed" else "Pendente",
                        "Observação": data.get("note", ""),
                        "Uso de Mdist": ('Não utilizado — exclusão de projeto' if member['exclude_minor_distortion'] else 'Conforme o estado identificado'),
                    })
                table(rows, "Momentos críticos locais e distorcionais para os dois sentidos de flexão menor")
                st.caption(automatic_minor.get("method", "Análise de estabilidade elástica."))
                if member['exclude_minor_distortion']:
                    st.caption('Os críticos distorcionais permanecem registrados para consulta; não entram na resistência nem na rigidez de My deste cálculo.')
        if automatic_minor.get("status") == "pending":
            st.warning(automatic_minor.get("note", "O cálculo automático não concluiu todos os críticos necessários. Consulte a memória."))
        limitations = result.get("limitations", [])
        if limitations:
            with st.expander(f"Limitações e pontos a resolver ({len(limitations)})", expanded=overall != "pass"):
                for item in limitations:
                    st.markdown(f"- {item.get('message', '')}")
                    if item.get("reference"):
                        st.caption(item["reference"])
        with st.container(horizontal=True):
            st.download_button("Memória HTML", html_cached(result), file_name=f"{filename}_memoria.html",
                               mime="text/html", icon=":material/description:", key="download_html", on_click="ignore")
            st.download_button("Resultado JSON", report_json(result), file_name=f"{filename}_resultado.json",
                               mime="application/json", icon=":material/download:", key="download_result", on_click="ignore")
        view = st.segmented_control("Explorar resultado", ["Verificações", "Diagramas", "Memória", "Combinações"],
                                     default="Verificações", required=True, key="result_view")
        if view == "Verificações":
            figure = utilization_figure(checks)
            if figure:
                st.plotly_chart(figure, key="utilization_plot", config=PLOT_CONFIG,
                                alt="Maiores utilizações calculadas em comparação com o limite um")
            table([{"Verificação": item.get("label"), "Caso": item.get("case_id"),
                    "Estado": ('Atende ao escopo adotado' if item.get('conditional') and item.get('status')=='pass' else STATUS.get(item.get("status"), "Pendente")),
                    "Solicitação": number(item.get("demand")), "Resistência / limite": number(item.get("capacity")),
                    "Unidade": item.get("unit", ""), "Utilização": number(item.get("utilization")),
                    "Referência": item.get("reference", ""), "Observação": item.get("note", "")}
                   for item in checks], "Verificações resistentes e de serviço por caso de carregamento")
            st.subheader("Cobertura do cálculo")
            table([{"Verificação": item.get("verification"), "Estado": STATUS.get(item.get("status"), item.get("status")),
                    "Observação": item.get("note", ""), "Referência": item.get("reference", "")}
                   for item in result.get("coverage", [])], "Verificações cobertas e pendentes")
        elif view == "Diagramas":
            diagrams = result.get("diagrams", [])
            if diagrams:
                selected = st.selectbox("Caso de carregamento", range(len(diagrams)), key="diagram_selection",
                                        format_func=lambda i: f"{diagrams[i]['case_id']} · {diagrams[i].get('label', '')}")
                diagram = diagrams[selected]
                quantity = st.segmented_control("Grandeza", ["moment", "shear", "deflection"], required=True,
                                                default="moment", key="diagram_quantity",
                                                format_func=lambda value: {"moment": "Momento", "shear": "Cortante", "deflection": "Flecha"}[value])
                fields = {"moment": ["Mx_kNm", "My_kNm"], "shear": ["Vx_kN", "Vy_kN"], "deflection": ["dx_mm", "dy_mm"]}[quantity]
                if any(diagram.get(field) for field in fields):
                    quantity_label = {"moment": "momento fletor", "shear": "força cortante", "deflection": "deslocamento"}[quantity]
                    st.plotly_chart(diagram_figure(diagram, quantity), config=PLOT_CONFIG, key="result_diagram",
                                    alt=f"Distribuição de {quantity_label} no vão para o caso {diagram['case_id']}")
                    st.caption("z começa no apoio esquerdo. As curvas conservam os sinais do caso; Mx/My e Vx/Vy são componentes distintas. Não combine máximos de posições diferentes como um par concomitante exato.")
                else:
                    st.info("Esta grandeza não está disponível para o caso selecionado. Consulte a memória e as pendências.")
            table([{"Caso": item.get("label", item.get("id")), "Estado": ('Atende ao escopo adotado' if item.get('conditional') and item.get('status')=='pass' else STATUS.get(item.get("status"), "Pendente")),
                    "δx (mm)": number(item.get("dx_mm")), "Limite x (mm)": number(item.get("limit_x_mm")),
                    "δy (mm)": number(item.get("dy_mm")), "Limite y (mm)": number(item.get("limit_y_mm")),
                    "δ vertical (mm)": number(item.get("dvertical_mm")),
                    "Limite vertical (mm)": number(item.get("limit_vertical_mm")),
                    "Observação": item.get("note", "")}
                   for item in result.get("service_cases", [])], "Deslocamentos e limites das combinações de serviço")
            st.caption("δx e δy são componentes locais. Sob gravidade, a verificação vertical é apresentada separadamente; na sucção isolada, aplica-se o critério normal à cobertura.")
        elif view == "Memória":
            memory = result.get("memory", [])
            query = st.text_input("Filtrar a memória", placeholder="Ex.: flambagem, seção, ELU", key="memory_search")
            visible = [item for item in memory if not query or query.casefold() in " ".join(str(v) for v in item.values()).casefold()]
            st.caption(f"{len(visible)} de {len(memory)} registros. O download HTML contém a memória completa.")
            for index, item in enumerate(visible):
                with st.expander(str(item.get("title", f"Etapa {index + 1}"))):
                    for field in ["formula", "substitution"]:
                        if item.get(field):
                            expression = str(item[field])
                            if "\\" in expression:
                                st.latex(expression)
                            else:
                                st.code(expression, language=None, wrap_lines=True)
                    if item.get("result") not in (None, ""):
                        st.markdown(f"**Resultado:** {number(item['result']) if isinstance(item['result'], (int, float)) else item['result']} {item.get('unit', '')}")
                    if item.get("reference"):
                        st.caption(str(item["reference"]))
        else:
            table([{"Caso": item.get("id"), "Descrição": item.get("label"),
                    "Tipo": {"ULS": "ELU", "SLS": "ELS"}.get(item.get("kind"), item.get("kind")),
                    "qx (kN/m)": number(item.get("qx_kNm")), "qy (kN/m)": number(item.get("qy_kNm")),
                    "Px (kN)": number(item.get("px_kN")), "Py (kN)": number(item.get("py_kN")),
                    "a (m)": number(item.get("a_m")), "N (kN)": number(item.get("nsd_kN")),
                    "Composição": item.get("description", "")}
                   for item in result.get("combinations", [])], "Combinações e esforços concomitantes utilizados no cálculo")
            st.caption("Pressão e sucção são alternativas. A força de manutenção é alternativa a Q distribuída. Os relatórios preservam as combinações usadas em cada verificação.")
