export default function App() {
  const cyan = "#21d4fd";
  const green = "#69f069";
  const purple = "#ce93d8";
  const yellow = "#ffd200";
  const orange = "#f7971e";
  const red = "#ff6b6b";
  const teal = "#80cbc4";

  const Tip = ({ color }) => (
    <div
      style={{
        width: 0,
        height: 0,
        borderTop: "5px solid transparent",
        borderBottom: "5px solid transparent",
        borderLeft: `7px solid ${color}`,
        flexShrink: 0,
      }}
    />
  );

  const Arr = ({ color, label }) => (
    <div
      style={{
        flexShrink: 0,
        width: 36,
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
      }}
    >
      <div style={{ display: "flex", alignItems: "center", width: "100%" }}>
        <div style={{ flex: 1, height: 2, background: color }} />
        <Tip color={color} />
      </div>
      {label && (
        <div
          style={{ fontSize: 6.5, color, marginTop: 2, whiteSpace: "nowrap" }}
        >
          {label}
        </div>
      )}
    </div>
  );

  const Box = ({ w, bg, border, nameColor, name, sub }) => (
    <div
      style={{
        flexShrink: 0,
        width: w || 160,
        borderRadius: 6,
        padding: "7px 10px",
        textAlign: "center",
        background: bg,
        border: `1.5px solid ${border}`,
      }}
    >
      <div style={{ fontSize: 10, fontWeight: 700, color: nameColor }}>
        {name}
      </div>
      {sub && (
        <div style={{ fontSize: 7.5, color: "#5a7a99", marginTop: 2 }}>
          {sub}
        </div>
      )}
    </div>
  );

  const Out = ({ bg, border, nameColor, name, sub }) => (
    <div
      style={{
        flexShrink: 0,
        width: 165,
        borderRadius: 8,
        padding: "9px 12px",
        textAlign: "center",
        background: bg,
        border: `2px solid ${border}`,
      }}
    >
      <div style={{ fontSize: 10, fontWeight: 800, color: nameColor }}>
        {name}
      </div>
      <div
        style={{
          fontSize: 7.5,
          color: "#5a7a99",
          marginTop: 3,
          lineHeight: 1.4,
        }}
      >
        {sub}
      </div>
    </div>
  );

  const Label = ({ bg, border, color, text }) => (
    <div
      style={{
        writingMode: "vertical-rl",
        textOrientation: "mixed",
        transform: "rotate(180deg)",
        fontSize: 7,
        fontWeight: 800,
        letterSpacing: 1.2,
        textTransform: "uppercase",
        whiteSpace: "nowrap",
        padding: "6px 4px",
        borderRadius: 4,
        marginRight: 6,
        flexShrink: 0,
        background: bg,
        color,
        border: `1px solid ${border}`,
      }}
    >
      {text}
    </div>
  );

  const Row = ({ children }) => (
    <div style={{ display: "flex", alignItems: "center", gap: 0 }}>
      {children}
    </div>
  );

  const sharedStart = (pipeColor, consumeLabel) => (
    <>
      <Box
        w={130}
        bg="#0a2540"
        border="#1e5080"
        nameColor="#4fc3f7"
        name="5 Data APIs"
        sub="Sportradar / ESPN / NBA"
      />
      <Arr color={orange} label="AMQP push" />
      <Box
        w={130}
        bg="#1a0e00"
        border={orange}
        nameColor="#ffd54f"
        name="Kafka Producer"
        sub="Fingerprint dedup"
      />
      <Arr color={yellow} label="publish" />
      <Box
        w={140}
        bg="#1a1000"
        border={yellow}
        nameColor={yellow}
        name="Kafka MSK"
        sub="6 brokers - 50+ topics - 50K msg/s"
      />
      <Arr color={pipeColor} label={consumeLabel || "consume"} />
    </>
  );

  const InfraCard = ({ name, sub, nameColor }) => (
    <div
      style={{
        background: "#0a2540",
        border: "1.5px solid #1e5080",
        borderRadius: 6,
        padding: "5px 8px",
        textAlign: "center",
      }}
    >
      <div
        style={{ fontSize: 8, fontWeight: 700, color: nameColor || "#4fc3f7" }}
      >
        {name}
      </div>
      <div style={{ fontSize: 7, color: "#5a7a99" }}>{sub}</div>
    </div>
  );

  const Stat = ({ num, desc }) => (
    <div style={{ textAlign: "center" }}>
      <div style={{ fontSize: 15, fontWeight: 800, color: yellow }}>{num}</div>
      <div style={{ fontSize: 7, color: "#5a7a99" }}>{desc}</div>
    </div>
  );

  const Divider = () => (
    <div style={{ width: 1, background: "#1e3a5f", alignSelf: "stretch" }} />
  );

  return (
    <div
      style={{
        background: "#0a0e1a",
        minHeight: "100vh",
        padding: 16,
        fontFamily: "Arial,sans-serif",
        color: "#e0e6f0",
        overflowX: "auto",
      }}
    >
      <h1
        style={{
          textAlign: "center",
          fontSize: 18,
          fontWeight: 900,
          color: yellow,
          marginBottom: 4,
        }}
      >
        Production Scale Architecture - 365Scores Style
      </h1>
      <p
        style={{
          textAlign: "center",
          fontSize: 9,
          color: "#5a7a99",
          marginBottom: 10,
        }}
      >
        10M+ MAU - 99.95% SLA - Sub-1s latency - Multi-region - AWS
      </p>

      <div
        style={{
          display: "flex",
          justifyContent: "center",
          gap: 6,
          flexWrap: "wrap",
          marginBottom: 14,
        }}
      >
        {[
          ["Kafka MSK", "#1a3a5c", "#4fc3f7"],
          ["WebSocket Push", "#0a1a2e", cyan],
          ["PySpark Streaming", "#0e1a0a", green],
          ["Mobile Push", "#1a0a1a", purple],
          ["EKS Kubernetes", "#0a1a14", teal],
        ].map(([t, bg, c]) => (
          <span
            key={t}
            style={{
              padding: "2px 9px",
              borderRadius: 20,
              fontSize: 8,
              fontWeight: 700,
              background: bg,
              color: c,
              border: `1px solid ${c}`,
            }}
          >
            {t}
          </span>
        ))}
      </div>

      <div style={{ overflowX: "auto", paddingBottom: 12 }}>
        <div
          style={{
            display: "flex",
            flexDirection: "column",
            gap: 10,
            width: "max-content",
          }}
        >
          {/* PIPELINE 1 - Live UI */}
          <Row>
            <Label
              bg="#0a1a2e"
              border={cyan + "55"}
              color={cyan}
              text="P1 - Live UI"
            />
            {sharedStart(cyan)}
            <Box
              bg="#0a1a2e"
              border={cyan + "55"}
              nameColor="#4fc3f7"
              name="Kafka Consumer"
              sub="kafka_listener() - all topics"
            />
            <Arr color={cyan} />
            <Box
              bg="#1a0a0a"
              border={red + "55"}
              nameColor={red}
              name="Redis Pub/Sub"
              sub="Cache layer - TTL 1-3s"
            />
            <Arr color={cyan} />
            <Box
              bg="#0a1a2e"
              border={cyan + "55"}
              nameColor="#4fc3f7"
              name="WS Cluster"
              sub="6 nodes - 100K concurrent"
            />
            <Arr color={cyan} />
            <Box
              bg="#0a1a14"
              border={teal + "55"}
              nameColor={teal}
              name="CloudFront CDN"
              sub="Global edge - 10 TB/mo"
            />
            <Arr color={cyan} />
            <Out
              bg="#0a1a2e"
              border={cyan}
              nameColor={cyan}
              name="Live Browser"
              sub="WebSocket push - under 100ms"
            />
          </Row>

          {/* PIPELINE 2 - Spark */}
          <Row>
            <Label
              bg="#0e1a0a"
              border={green + "55"}
              color={green}
              text="P2 - Spark"
            />
            {sharedStart(green)}
            <Box
              bg="#0e1a0a"
              border={green + "55"}
              nameColor="#a5d6a7"
              name="Kafka Source"
              sub="stream_to_postgres.py"
            />
            <Arr color={green} />
            <Box
              bg="#0e1a0a"
              border={green + "55"}
              nameColor="#a5d6a7"
              name="Spark Cluster"
              sub="3x r6g.xlarge - foreachBatch"
            />
            <Arr color={green} />
            <Box
              bg="#0e1a0a"
              border={green + "55"}
              nameColor="#a5d6a7"
              name="JDBC Sink"
              sub="pg_write() - micro-batch"
            />
            <Arr color={green} />
            <Box
              bg="#0e1a0a"
              border={green + "55"}
              nameColor="#a5d6a7"
              name="Read Replicas x2"
              sub="db.r6g.large - query layer"
            />
            <Arr color={green} />
            <Out
              bg="#0e1a0a"
              border={green}
              nameColor={green}
              name="PostgreSQL Multi-AZ"
              sub="game_scores - match_events - period_scores"
            />
          </Row>

          {/* PIPELINE 3 - Mobile */}
          <Row>
            <Label
              bg="#1a0a1a"
              border={purple + "55"}
              color={purple}
              text="P3 - Mobile"
            />
            {sharedStart(purple)}
            <Box
              bg="#1a0a1a"
              border={purple + "55"}
              nameColor="#e1bee7"
              name="Kafka Consumer"
              sub="goal / event trigger"
            />
            <Arr color={purple} />
            <Box
              bg="#1a0a1a"
              border={purple + "55"}
              nameColor="#e1bee7"
              name="Notification Rules"
              sub="DynamoDB - user prefs"
            />
            <Arr color={purple} />
            <Box
              bg="#1a0a1a"
              border={purple + "55"}
              nameColor="#e1bee7"
              name="FCM / APNs"
              sub="Firebase - OneSignal 500M/mo"
            />
            <Arr color={purple} />
            <Box
              bg="#1a0a1a"
              border={purple + "55"}
              nameColor="#e1bee7"
              name="Push Delivery"
              sub="OneSignal Growth - $12K/mo"
            />
            <Arr color={purple} />
            <Out
              bg="#1a0a1a"
              border={purple}
              nameColor={purple}
              name="iOS + Android"
              sub="React Native - 10M+ users"
            />
          </Row>

          {/* PIPELINE 4 - Batch */}
          <Row>
            <Label
              bg="#120a1a"
              border={purple + "55"}
              color={purple}
              text="P4 - Batch"
            />
            <Box
              w={130}
              bg="#0a2540"
              border="#1e5080"
              nameColor="#4fc3f7"
              name="5 Data APIs"
              sub="nba_api + ESPN direct"
            />
            <Arr color={purple} label="poll 6h" />
            <Box
              w={130}
              bg="#120a1a"
              border={purple + "55"}
              nameColor={purple}
              name="Airflow Scheduler"
              sub="cron trigger every 6h"
            />
            <Arr color={purple} />
            <Box
              w={140}
              bg="#120a1a"
              border={purple + "55"}
              nameColor={purple}
              name="Stats Fetcher"
              sub="fetch_stats.py - all leagues"
            />
            <Arr color={purple} />
            <Box
              bg="#120a1a"
              border={purple + "55"}
              nameColor={purple}
              name="NBA Stats Fetch"
              sub="nba_api live endpoints"
            />
            <Arr color={purple} />
            <Box
              bg="#120a1a"
              border={purple + "55"}
              nameColor={purple}
              name="ESPN Stats Fetch"
              sub="NFL + PL + Liga + UCL"
            />
            <Arr color={purple} />
            <Box
              bg="#120a1a"
              border={purple + "55"}
              nameColor={purple}
              name="psycopg2 upsert"
              sub="upsert_stats() direct"
            />
            <Arr color={purple} />
            <Box
              bg="#120a1a"
              border={purple + "55"}
              nameColor={purple}
              name="Transform + Validate"
              sub="Data quality checks"
            />
            <Arr color={purple} />
            <Out
              bg="#0e1a0a"
              border={green}
              nameColor={green}
              name="PostgreSQL"
              sub="player_season_stats table"
            />
          </Row>
        </div>
      </div>

      {/* INFRA */}
      <div
        style={{
          background: "#0a0d15",
          border: "1px solid #1e2a3a",
          borderRadius: 9,
          padding: "8px 12px",
          marginTop: 10,
        }}
      >
        <div
          style={{
            fontSize: 7.5,
            fontWeight: 800,
            letterSpacing: 1.5,
            textTransform: "uppercase",
            color: teal,
            marginBottom: 6,
            textAlign: "center",
          }}
        >
          Infrastructure - AWS EKS Kubernetes - Multi-AZ - Auto-scaling -
          $8,620/month
        </div>
        <div
          style={{
            display: "flex",
            gap: 6,
            flexWrap: "wrap",
            justifyContent: "center",
          }}
        >
          {[
            ["CloudFront CDN", "Edge caching", teal],
            ["ALB", "Load balancer", "#4fc3f7"],
            ["EKS Cluster", "Kubernetes", "#4fc3f7"],
            ["IAM + KMS", "Security", "#ffd54f"],
            ["RDS Multi-AZ", "PostgreSQL HA", "#a5d6a7"],
            ["ElastiCache", "Redis 6-node", red],
            ["DynamoDB", "User prefs", "#e1bee7"],
            ["S3 + Athena", "Archival + analytics", teal],
            ["Route 53", "DNS failover", "#4fc3f7"],
            ["WAF + Shield", "DDoS protection", "#4fc3f7"],
            ["GitHub Actions", "CI/CD pipeline", "#4fc3f7"],
          ].map(([n, s, c]) => (
            <InfraCard key={n} name={n} sub={s} nameColor={c} />
          ))}
        </div>
      </div>

      {/* STATS */}
      <div
        style={{
          display: "flex",
          justifyContent: "center",
          gap: 14,
          flexWrap: "wrap",
          padding: "8px 12px",
          marginTop: 10,
          background: "#0a0e1a",
          border: "1px solid #1e2a3a",
          borderRadius: 10,
        }}
      >
        {[
          ["10M+", "MAU Target"],
          ["99.95%", "SLA"],
          ["<1s", "Latency"],
          ["6", "Kafka Brokers"],
          ["50+", "Topics"],
          ["50K", "msg/s"],
          ["$8.6K", "Infra/mo"],
          ["9", "Team Size"],
          ["$2.77M", "Year 1 Cost"],
        ].map(([n, d], i, arr) => (
          <div
            key={d}
            style={{ display: "flex", alignItems: "center", gap: 14 }}
          >
            <Stat num={n} desc={d} />
            {i < arr.length - 1 && <Divider />}
          </div>
        ))}
      </div>
    </div>
  );
}
