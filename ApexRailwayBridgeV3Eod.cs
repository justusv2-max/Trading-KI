using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.ComponentModel.DataAnnotations;
using System.Globalization;
using System.Linq;
using System.Net.Http;
using System.Text;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using ATAS.DataFeedsCore;
using ATAS.Strategies.Chart;

namespace OpenAI.ApexBridge
{
    public sealed class ApexRailwayBridgeV3Eod : ChartStrategy
    {
        private const decimal Quantity = 1m;
        private const decimal Tick = 0.01m;
        private readonly HttpClient _http = new HttpClient { Timeout = TimeSpan.FromSeconds(10) };
        private readonly ConcurrentDictionary<string, TradeCtx> _trades = new();
        private readonly HashSet<string> _seenS3 = new(StringComparer.Ordinal);
        private readonly object _seenLock = new();
        private CancellationTokenSource? _cts;
        private Task? _pollTask;
        private DateTimeOffset _lastErrorNotice = DateTimeOffset.MinValue;
        private volatile bool _riskSyncHealthy = true;

        [Display(Name = "Railway Basis-URL", GroupName = "Bridge", Order = 10)]
        public string RailwayBaseUrl { get; set; } = "https://web-production-9acfcd.up.railway.app";

        [Display(Name = "Webhook Secret", GroupName = "Bridge", Order = 20)]
        public string WebhookSecret { get; set; } = "";

        [Display(Name = "Erlaubte Konten (; getrennt)", GroupName = "Sicherheit", Order = 30)]
        public string AllowedAccounts { get; set; } = "";

        [Display(Name = "Live Trading aktiv", GroupName = "Sicherheit", Order = 40)]
        public bool ArmLiveTrading { get; set; } = false;

        [Display(Name = "Nur CL", GroupName = "Sicherheit", Order = 50)]
        public bool EnforceCL { get; set; } = true;

        [Display(Name = "Max. S3-Signalalter (Sek.)", GroupName = "Sicherheit", Order = 60)]
        public int MaxSignalAgeSeconds { get; set; } = 75;

        [Display(Name = "Polling (ms)", GroupName = "Bridge", Order = 70)]
        public int PollMilliseconds { get; set; } = 1500;

        [Display(Name = "Apex EOD Profil", GroupName = "Sicherheit", Order = 80)]
        public string AccountProfile { get; set; } = "50K_EOD_EVAL";

        [Display(Name = "Apex Vendor", GroupName = "Sicherheit", Order = 90)]
        public string ApexVendor { get; set; } = "RITHMIC";

        public ApexRailwayBridgeV3Eod() : base(useCandles: true) { Name = "Apex Railway Bridge V3 EOD"; }
        protected override void OnCalculate(int bar, decimal value) { }

        protected override void OnStarted()
        {
            base.OnStarted();
            if (Portfolio == null) { StopWithNotification("Kein Konto/Portfolio gewählt."); return; }
            if (Security == null) { StopWithNotification("Kein Instrument gewählt."); return; }
            if (!AccountAllowed(Portfolio.AccountID)) { StopWithNotification($"Konto {Portfolio.AccountID} ist nicht in 'Erlaubte Konten' eingetragen."); return; }
            if (EnforceCL && !LooksLikeCL(Security)) { StopWithNotification($"Falsches Instrument: {SecurityLabel(Security)}. Nur CL erlaubt."); return; }
            if (!Uri.TryCreate(RailwayBaseUrl, UriKind.Absolute, out _)) { StopWithNotification("Railway Basis-URL ungültig."); return; }
            if (string.IsNullOrWhiteSpace(WebhookSecret)) { StopWithNotification("Webhook Secret fehlt."); return; }
            _http.DefaultRequestHeaders.Remove("x-webhook-secret");
            _http.DefaultRequestHeaders.Add("x-webhook-secret", WebhookSecret.Trim());
            _cts = new CancellationTokenSource();
            _pollTask = Task.Run(() => PollLoop(_cts.Token));
            RaiseShowNotification(ArmLiveTrading
                ? $"Bridge V3 LIVE: {Portfolio.AccountID}, {AccountProfile}, {SecurityLabel(Security)}, 1 CL."
                : $"Bridge V3 SAFE MODE: {Portfolio.AccountID}, {AccountProfile}. Live Trading AUS.");
        }
        protected override void OnStopping() { try { _cts?.Cancel(); } catch { } base.OnStopping(); }
        protected override void OnStopped() { try { _cts?.Cancel(); } catch { } base.OnStopped(); }

        private async Task PollLoop(CancellationToken ct)
        {
            while (!ct.IsCancellationRequested)
            {
                try
                {
                    var url = RailwayBaseUrl.TrimEnd('/') + "/bridge/status?account_id=" + Uri.EscapeDataString(Portfolio.AccountID) + "&profile=" + Uri.EscapeDataString(AccountProfile) + "&vendor=" + Uri.EscapeDataString(ApexVendor);
                    var json = await _http.GetStringAsync(url, ct);
                    var st = JsonSerializer.Deserialize<BridgeStatus>(json, JsonOptions);
                    if (st == null || !st.ok || !st.ready || !string.Equals(st.mode, "APEX", StringComparison.OrdinalIgnoreCase))
                    { await Delay(ct); continue; }
                    if (!ArmLiveTrading || !_riskSyncHealthy) { await Delay(ct); continue; }
                    await ReconcileS2(st.active_s2_limits ?? new List<BridgeSignal>());
                    foreach (var s in st.s3_commands ?? new List<BridgeSignal>()) await HandleS3(s, st.server_time);
                }
                catch (OperationCanceledException) when (ct.IsCancellationRequested) { }
                catch (Exception ex)
                {
                    var now = DateTimeOffset.UtcNow;
                    if (now - _lastErrorNotice > TimeSpan.FromSeconds(30)) { _lastErrorNotice = now; RaiseShowNotification($"Bridge V3 Polling: {ex.Message}"); }
                }
                await Delay(ct);
            }
        }
        private Task Delay(CancellationToken ct) => Task.Delay(Math.Max(250, PollMilliseconds), ct);

        private async Task ReconcileS2(List<BridgeSignal> active)
        {
            var ids = new HashSet<string>(active.Select(x => x.signal_id), StringComparer.Ordinal);
            foreach (var kv in _trades.ToArray())
            {
                var ctx = kv.Value;
                if (ctx.Signal.kind != "S2_LIMIT" || ctx.Entry == null || ctx.Entry.Status() == OrderStatus.Filled) continue;
                if (!ids.Contains(kv.Key) && ctx.Entry.State == OrderStates.Active) await SafeCancel(ctx.Entry, kv.Key);
            }
            foreach (var s in active)
            {
                if (_trades.ContainsKey(s.signal_id)) continue;
                if (!Validate(s, out var why)) { RaiseShowNotification($"S2 verworfen {s.signal_id}: {why}"); continue; }
                await PlaceEntry(s, market:false);
            }
        }

        private async Task HandleS3(BridgeSignal s, double serverNow)
        {
            lock (_seenLock) { if (_seenS3.Contains(s.signal_id)) return; }
            if (!Validate(s, out var why)) { MarkS3(s.signal_id); RaiseShowNotification($"S3 verworfen {s.signal_id}: {why}"); return; }
            var age = serverNow - s.created_epoch;
            if (age < -5 || age > Math.Min(MaxSignalAgeSeconds, s.max_age_seconds > 0 ? s.max_age_seconds : MaxSignalAgeSeconds)) { MarkS3(s.signal_id); return; }
            MarkS3(s.signal_id);
            await PlaceEntry(s, market:true);
        }

        private async Task PlaceEntry(BridgeSignal s, bool market)
        {
            if (_trades.ContainsKey(s.signal_id)) return;
            var dir = s.direction == 1 ? OrderDirections.Buy : OrderDirections.Sell;
            var order = new Order
            {
                Portfolio = Portfolio, Security = Security, AccountID = Portfolio.AccountID,
                Direction = dir, Type = market ? OrderTypes.Market : OrderTypes.Limit,
                QuantityToFill = Quantity, Comment = $"RWV2:{s.signal_id}:ENTRY"
            };
            if (!market) order.Price = ShrinkPrice(s.entry);
            var ctx = new TradeCtx(s) { Entry = order };
            if (!_trades.TryAdd(s.signal_id, ctx)) return;
            try
            {
                await OpenOrderAsync(order);
                RaiseShowNotification($"{s.setup} {(s.direction==1?"LONG":"SHORT")} {(market?"MARKET":"LIMIT "+s.entry.ToString("F2",CultureInfo.InvariantCulture))} | {s.signal_id}");
            }
            catch (Exception ex) { _trades.TryRemove(s.signal_id, out _); RaiseShowNotification($"ENTRY FEHLER {s.signal_id}: {ex.Message}"); }
        }

        protected override void OnNewMyTrade(MyTrade myTrade)
        {
            base.OnNewMyTrade(myTrade);
            if (myTrade?.Order == null) return;
            foreach (var kv in _trades.ToArray())
            {
                var ctx = kv.Value;
                if (ctx.Entry != null && ReferenceEquals(myTrade.Order, ctx.Entry))
                {
                    ctx.FillPrice = myTrade.Price;
                    if (!ctx.EntryReported) { ctx.EntryReported = true; _ = PostExecution(ctx, "ENTRY", myTrade.Price); }
                    if (!ctx.BracketSent) _ = EnsureBracket(ctx);
                    return;
                }
                if ((ctx.Stop != null && ReferenceEquals(myTrade.Order, ctx.Stop)) || (ctx.Target != null && ReferenceEquals(myTrade.Order, ctx.Target)))
                {
                    if (!ctx.ExitReported) { ctx.ExitReported = true; _ = PostExecution(ctx, "EXIT", myTrade.Price); }
                    return;
                }
            }
        }

        protected override void OnOrderChanged(Order order)
        {
            base.OnOrderChanged(order);
            foreach (var kv in _trades.ToArray())
            {
                var ctx = kv.Value;
                if (ReferenceEquals(order, ctx.Stop) && order.Status() == OrderStatus.Filled) { _ = CancelSibling(ctx.Target); _trades.TryRemove(kv.Key, out _); continue; }
                if (ReferenceEquals(order, ctx.Target) && order.Status() == OrderStatus.Filled) { _ = CancelSibling(ctx.Stop); _trades.TryRemove(kv.Key, out _); continue; }
                if (ReferenceEquals(order, ctx.Entry) && order.Status() == OrderStatus.Canceled)
                { _ = PostExecution(ctx, "CANCEL", 0m); _trades.TryRemove(kv.Key, out _); }
            }
        }

        private async Task EnsureBracket(TradeCtx ctx)
        {
            lock (ctx.Sync) { if (ctx.BracketSent) return; ctx.BracketSent = true; }
            var s=ctx.Signal; var fill=ctx.FillPrice;
            if (fill <= 0) { lock(ctx.Sync) ctx.BracketSent=false; RaiseShowNotification($"Kein Fillpreis für {s.signal_id}; Bracket nicht gesendet."); return; }
            decimal stop, target;
            if (s.kind == "S2_LIMIT" && s.stop > 0 && s.target > 0) { stop=s.stop; target=s.target; }
            else { stop=fill - s.direction*s.sl_ticks*Tick; target=fill + s.direction*s.tp_ticks*Tick; }
            var exitDir=s.direction==1?OrderDirections.Sell:OrderDirections.Buy; var oco=$"RWV2-{s.signal_id}";
            var sl=new Order { Portfolio=Portfolio,Security=Security,AccountID=Portfolio.AccountID,Direction=exitDir,Type=OrderTypes.Stop,TriggerPrice=ShrinkPrice(stop),QuantityToFill=Quantity,OCOGroup=oco,AutoCancel=true,Comment=$"RWV2:{s.signal_id}:STOP" };
            var tp=new Order { Portfolio=Portfolio,Security=Security,AccountID=Portfolio.AccountID,Direction=exitDir,Type=OrderTypes.Limit,Price=ShrinkPrice(target),QuantityToFill=Quantity,OCOGroup=oco,AutoCancel=true,Comment=$"RWV2:{s.signal_id}:TARGET" };
            ctx.Stop=sl;ctx.Target=tp;
            try { await OpenOrderAsync(sl); await OpenOrderAsync(tp); RaiseShowNotification($"Bracket {s.signal_id}: SL {stop:F2} / TP {target:F2}"); }
            catch(Exception ex) { RaiseShowNotification($"BRACKET FEHLER {s.signal_id}: {ex.Message}"); }
        }

        private async Task PostExecution(TradeCtx ctx, string ev, decimal fill)
        {
            var payload = new
            {
                account_id = Portfolio?.AccountID ?? "",
                profile = AccountProfile,
                vendor = ApexVendor,
                signal_id = ctx.Signal.signal_id,
                setup = ctx.Signal.setup,
                direction = ctx.Signal.direction,
                @event = ev,
                fill_price = ev == "CANCEL" ? (decimal?)null : fill,
                timestamp_utc = DateTimeOffset.UtcNow.ToString("O", CultureInfo.InvariantCulture)
            };
            var json = JsonSerializer.Serialize(payload);
            Exception? last = null;
            for (var attempt = 1; attempt <= 3; attempt++)
            {
                try
                {
                    using var body = new StringContent(json, Encoding.UTF8, "application/json");
                    using var resp = await _http.PostAsync(RailwayBaseUrl.TrimEnd('/') + "/bridge/execution", body);
                    if (resp.IsSuccessStatusCode) { _riskSyncHealthy = true; return; }
                    last = new Exception($"HTTP {(int)resp.StatusCode}");
                }
                catch (Exception ex) { last = ex; }
                await Task.Delay(400 * attempt);
            }
            _riskSyncHealthy = false;
            RaiseShowNotification($"RISK-SYNC AUSFALL: keine neuen Entries bis Neustart. {ev} {ctx.Signal.signal_id}: {last?.Message}");
        }

        private async Task SafeCancel(Order? o,string id) { if(o==null)return; try { if(o.State==OrderStates.Active) await CancelOrderAsync(o); } catch(Exception ex){RaiseShowNotification($"CANCEL FEHLER {id}: {ex.Message}");} }
        private async Task CancelSibling(Order? o) { if(o==null)return; try { if(o.State==OrderStates.Active) await CancelOrderAsync(o); } catch(Exception ex){RaiseShowNotification($"OCO CANCEL: {ex.Message}");} }
        protected override void OnOrderRegisterFailed(Order order,string message){base.OnOrderRegisterFailed(order,message);RaiseShowNotification($"ORDER ABGELEHNT: {order.Comment} | {message}");}
        protected override void OnOrderCancelFailed(Order order,string message){base.OnOrderCancelFailed(order,message);RaiseShowNotification($"CANCEL ABGELEHNT: {order.Comment} | {message}");}

        private bool AccountAllowed(string? id)
        {
            if (string.IsNullOrWhiteSpace(id) || string.IsNullOrWhiteSpace(AllowedAccounts)) return false;
            return AllowedAccounts.Split(new[]{';',','},StringSplitOptions.RemoveEmptyEntries).Select(x=>x.Trim()).Any(x=>string.Equals(x,id,StringComparison.OrdinalIgnoreCase));
        }
        private static bool Validate(BridgeSignal s,out string reason)
        {
            reason=""; if(string.IsNullOrWhiteSpace(s.signal_id)){reason="signal_id fehlt";return false;}
            if(s.direction!=1&&s.direction!=-1){reason="Richtung ungültig";return false;}
            var allowed=new HashSet<string>(StringComparer.OrdinalIgnoreCase){"HV-1","HV-2","LV-1","LV-2","LV-3","S3-A","S3-B","S3-C","S3-D"};
            if(!allowed.Contains(s.setup??"")){reason="Setup unbekannt";return false;}
            if(s.sl_ticks<1||s.tp_ticks<1){reason="SL/TP ungültig";return false;}
            if(s.kind=="S2_LIMIT" && (s.entry<=0||s.stop<=0||s.target<=0)){reason="S2 Preis fehlt";return false;}
            return true;
        }
        private static bool LooksLikeCL(Security s)
        {
            foreach(var raw in new[]{s.Code,s.SecurityId,s.Instrument,s.ToString()}){if(string.IsNullOrWhiteSpace(raw))continue;var v=raw.Trim().ToUpperInvariant();if(v.StartsWith("#"))v=v.Substring(1);if(v=="CL"||(v.StartsWith("CL")&&v.Length>=3&&"FGHJKMNQUVXZ".Contains(v[2])))return true;}return false;
        }
        private static string SecurityLabel(Security s)=>$"Code={s.Code}; SecurityId={s.SecurityId}; Instrument={s.Instrument}; Exchange={s.Exchange}";
        private void MarkS3(string id){lock(_seenLock){_seenS3.Add(id);if(_seenS3.Count>5000){_seenS3.Clear();_seenS3.Add(id);}}}
        private void StopWithNotification(string m){RaiseShowNotification(m);try{_cts?.Cancel();}catch{}}
        private static readonly JsonSerializerOptions JsonOptions=new(){PropertyNameCaseInsensitive=true};

        private sealed class BridgeStatus
        {
            public bool ok{get;set;} public bool ready{get;set;} public string mode{get;set;}=""; public double server_time{get;set;}
            public List<BridgeSignal>? s3_commands{get;set;} public List<BridgeSignal>? active_s2_limits{get;set;}
        }
        private sealed class BridgeSignal
        {
            public string signal_id{get;set;}=""; public string kind{get;set;}=""; public string setup{get;set;}=""; public int direction{get;set;}
            public decimal entry{get;set;} public decimal stop{get;set;} public decimal target{get;set;} public int sl_ticks{get;set;} public int tp_ticks{get;set;}
            public double created_epoch{get;set;} public int max_age_seconds{get;set;}=75;
        }
        private sealed class TradeCtx
        {
            public readonly object Sync=new(); public readonly BridgeSignal Signal; public Order? Entry; public Order? Stop; public Order? Target; public bool BracketSent; public bool EntryReported; public bool ExitReported; public decimal FillPrice;
            public TradeCtx(BridgeSignal s){Signal=s;}
        }
    }
}
