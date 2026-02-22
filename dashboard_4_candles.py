import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
from datetime import timedelta

# =========================
# PARÂMETROS ⇩
# =========================
ENTRADA_FIXA = 10.0     # Valor por entrada
PAYOUT = 0.8            # Payout (ex: 0.8 = 80% de retorno sobre vitória)
STOP_WIN = 100.0        # Stop win
STOP_LOSS = 50.0        # Stop loss

# =========================
# FUNÇÕES BASE
# =========================
def carregar_dados(uploaded_file):
    df = pd.read_csv(uploaded_file)
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    df = df.sort_values('timestamp').reset_index(drop=True)
    return df

def identificar_primes_candles_hora(df):
    df['hora'] = df['timestamp'].dt.floor('H')
    df['minuto'] = df['timestamp'].dt.minute
    primeiro_candle_hora = df[df['minuto'] == 0][['hora', 'open', 'close']].copy()
    primeiro_candle_hora['direcao'] = (primeiro_candle_hora['close'] > primeiro_candle_hora['open']).map({True:'compra', False:'venda'})
    return primeiro_candle_hora.set_index('hora')['direcao'].to_dict()

def backtest_4_candles(df, entrada, payout, stop_win, stop_loss):
    primeira_direcao_horas = identificar_primes_candles_hora(df)
    resultados = []
    banca = 0.0
    banco_evolucao = [banca]
    seq_perda = maior_seq_perda = 0
    drawdown_max = 0.0
    top_banca = 0.0

    time_pointer = df['timestamp'].dt.floor('H').min()
    end_time = df['timestamp'].dt.floor('H').max() + timedelta(hours=1)

    while time_pointer < end_time:
        session = df[(df['timestamp'] >= time_pointer) &
                     (df['timestamp'] < time_pointer + timedelta(hours=1))].copy()
        if session.empty or time_pointer not in primeira_direcao_horas:
            time_pointer += timedelta(hours=1)
            continue

        direcao_ref = primeira_direcao_horas[time_pointer]
        idx_ref = 0
        while idx_ref + 4 < len(session):
            idx_entrada = idx_ref + 4
            candle_entrada = session.iloc[idx_entrada]
            direcao = direcao_ref

            close_analisado = candle_entrada['close']
            open_analisado = candle_entrada['open']
            is_win = ((direcao == 'compra' and close_analisado > open_analisado) or
                      (direcao == 'venda' and close_analisado < open_analisado))

            resultado = {
                'timestamp': candle_entrada['timestamp'],
                'direcao': direcao,
                'win': is_win,
                'lucro': entrada * payout if is_win else -entrada,
                'banca': None, # Preenchido depois
            }
            resultados.append(resultado)

            banca += resultado['lucro']
            banco_evolucao.append(banca)
            resultado['banca'] = banca

            top_banca = max(top_banca, banca)
            drawdown = top_banca - banca
            drawdown_max = max(drawdown_max, drawdown)

            if is_win:
                seq_perda = 0
            else:
                seq_perda += 1
                maior_seq_perda = max(maior_seq_perda, seq_perda)

            if stop_win and banca >= stop_win:
                break
            if stop_loss and banca <= -stop_loss:
                break

            if close_analisado > open_analisado:
                direcao_ref = 'compra'
            elif close_analisado < open_analisado:
                direcao_ref = 'venda'
            idx_ref = idx_entrada
        time_pointer += timedelta(hours=1)
    trades = pd.DataFrame(resultados)
    # Drawdown
    picos = pd.Series(banco_evolucao).cummax()
    dd = picos - pd.Series(banco_evolucao)
    drawdown_maximo = dd.max()
    return trades, banco_evolucao, drawdown_maximo, maior_seq_perda

# =========================
# DASHBOARD STREAMLIT
# =========================
st.set_page_config(
    page_title="Dashboard 4 Candles",
    layout="centered",
    initial_sidebar_state="auto",
)

st.title("🚦 Dashboard Backtest Estratégia 4 Candles")
st.markdown(
    """
    Este painel executa backtests da estratégia dos 4 candles em dados de M1.<br>
    Faça upload do arquivo <b>CSV</b> (timestamp, open, high, low, close)!  
    """, unsafe_allow_html=True
)

# SIDEBAR
st.sidebar.header("Parâmetros do Backtest")
entrada = st.sidebar.number_input("Valor por entrada", min_value=1.0, value=ENTRADA_FIXA, step=1.0)
payout = st.sidebar.slider("Payout (%)", min_value=0.5, max_value=1.0, value=PAYOUT, step=0.01)
stop_win = st.sidebar.number_input("Stop Win (R$)", value=STOP_WIN, min_value=0.0)
stop_loss = st.sidebar.number_input("Stop Loss (R$)", value=STOP_LOSS, min_value=0.0)

uploaded_file = st.file_uploader("Carregue o arquivo CSV", type=["csv"])
if uploaded_file:
    df = carregar_dados(uploaded_file)
    with st.spinner("Processando..."):
        trades, banco_evolucao, drawdown_maximo, maior_seq_perda = backtest_4_candles(
            df, entrada, payout, stop_win, stop_loss
        )
    total = len(trades)
    vitorias = trades['win'].sum()
    derrotas = total - vitorias
    winrate = 100 * vitorias / total if total > 0 else 0.0
    lucro_bruto = vitorias * (entrada * payout)
    prejuizo_bruto = derrotas * entrada
    lucro_liquido = trades['lucro'].sum()

    # MÉTRICAS EM DESTAQUE
    col1, col2, col3 = st.columns(3)
    col1.metric("Operações", total)
    col2.metric("Winrate (%)", f"{winrate:.2f}")
    col3.metric("Lucro Líquido (R$)", f"{lucro_liquido:.2f}")

    col4, col5, col6 = st.columns(3)
    col4.metric("Lucro Bruto (R$)", f"{lucro_bruto:.2f}")
    col5.metric("Prejuízo Bruto (R$)", f"{prejuizo_bruto:.2f}")
    col6.metric("Drawdown Máx. (R$)", f"{drawdown_maximo:.2f}")

    st.info(f"Maior sequência de perdas: **{maior_seq_perda}**")

    # EVOLUÇÃO DA BANCA
    st.subheader("Evolução da banca")
    st.line_chart(banco_evolucao)

    # TABELA DE TRADES (opcional, mostra as últimas operações)
    with st.expander("📋 Últimas operações"):
        st.dataframe(
            trades[['timestamp', 'direcao', 'win', 'lucro', 'banca']].tail(30),
            use_container_width=True
        )

    # RELATÓRIO DETALHADO
    with st.expander("📊 Resumo estatístico completo"):
        st.write(
            f"""
            - Total de entradas: **{total}**
            - Vitórias: **{vitorias}**
            - Derrotas: **{derrotas}**
            - Winrate: **{winrate:.2f} %**
            - Lucro bruto: **R${lucro_bruto:.2f}**
            - Prejuízo bruto: **R${prejuizo_bruto:.2f}**
            - Lucro líquido: **R${lucro_liquido:.2f}**
            - Drawdown máximo: **R${drawdown_maximo:.2f}**
            - Maior sequência de perdas: **{maior_seq_perda}**
            """
        )

else:
    st.info("Por favor, carregue um arquivo CSV.")

st.markdown(
    """
    <br>
    <sub><i>Sugestão: utilize timeframe de 1 minuto (M1) com colunas: timestamp, open, high, low, close.</i></sub>
    """, unsafe_allow_html=True)
