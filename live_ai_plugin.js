// ============================================================================
// D-AUTO v7.3 (CHẾ ĐỘ TINH GỌN: CHỈ SKIP TÂN THỦ + NHẬP CODE + MỞ QUÀ GIFTCODE
// -> NẾU RA DƯƠNG TIỄN HOẶC TÔN NGỘ KHÔNG THÌ DỪNG LẠI NGAY!)
// ============================================================================
(function() {
  function attachCleanRerollPlugin() {
    var bot = window.HacTayDuAuto;
    if (!bot) {
      setTimeout(attachCleanRerollPlugin, 400);
      return;
    }

    bot.aiPluginVersion = "7.9-ANTI-DROP-550MS";
    bot.version = "7.9";
    bot.giftcodes = [
      "TOP1STORE", "HACTAYDU888", "TAYDUKI", "CHUONGCAM", "HTDCC999",
      "HOICHIEUTROIMUA", "45THANTUONG", "DUONGTIEN", "NATRA",
      "NGOKHONG", "THUANPHAM", "VAN97", "HOANGDZ",
      "NHANCAN111", "NHICAN222", "TICAN333", "THIETCAN444",
      "THANCAN555", "YCAN666", "DKT5K", "DKT10K",
      "DKT20K", "DKT30K", "DKT50K", "DAT100KDKT",
      "CCC2026", "NGOCKEN", "DOITAC666"
    ];

    // 1. TẮT NGAY TOÀN BỘ AI TỰ ĐÁNH ẢI / LEO THÁP / REROLL TỰ ĐỘNG!
    bot.aiAutoPlay = false;
    bot.autoCampaign = false;
    bot.autoTower = false;
    bot.autoRerollS2 = false;
    bot.rerollRunning = false;
    bot.lastRerollHero = "";
    bot.autoSkip = true;
    if (bot._aiMasterInterval) {
      clearInterval(bot._aiMasterInterval);
      bot._aiMasterInterval = null;
    }
    if (bot._aiWallRecoveryTimer) {
      clearTimeout(bot._aiWallRecoveryTimer);
      bot._aiWallRecoveryTimer = null;
    }
    if (bot.rerollWatchdogTimer) {
      clearTimeout(bot.rerollWatchdogTimer);
      bot.rerollWatchdogTimer = null;
    }
    try {
      localStorage.setItem("dauto_ai_play", "false");
      localStorage.setItem("dauto_campaign", "false");
      localStorage.setItem("dauto_tower", "false");
      localStorage.setItem("DAUTO_REROLL_S2", "0");
      localStorage.removeItem("DAUTO_WIN_HERO");
    } catch (e) {}
    if (bot.btnToggleAiPlay && bot.btnToggleAiPlay._refresh) {
      try { bot.btnToggleAiPlay._refresh(); } catch (e) {}
    }
    if (bot.btnToggleCampaign && bot.btnToggleCampaign._refresh) {
      try { bot.btnToggleCampaign._refresh(); } catch (e) {}
    }
    if (bot.btnToggleTower && bot.btnToggleTower._refresh) {
      try { bot.btnToggleTower._refresh(); } catch (e) {}
    }

    // 2. Multi-fallback getNetMsg()
    bot.getNetMsg = function() {
      if (typeof n !== "undefined" && n && (n.CG_CDK || n.sendData || n.connect)) return n;
      if (typeof window !== "undefined") {
        if (window.n && (window.n.CG_CDK || window.n.sendData || window.n.connect)) return window.n;
        if (window.zi && (window.zi.CG_CDK || window.zi.sendData || window.zi.connect)) return window.zi;
        if (window.NetMsg && (window.NetMsg.CG_CDK || window.NetMsg.sendData || window.NetMsg.connect)) return window.NetMsg;
      }
      return null;
    };

    bot.showToast = function(msg) {
      try {
        var pToast = (typeof P !== "undefined" && P && P.add) ? P : (typeof window !== "undefined" && window.P && window.P.add ? window.P : null);
        if (pToast && pToast.add) {
          pToast.add(msg);
        }
      } catch (e) {}
    };

    bot.setManualStatus = function(msg, color, durationMs) {
      this.manualStatusLockUntil = Date.now() + (durationMs || 6000);
      if (this.layaStatusTxt) {
        this.layaStatusTxt.text = msg;
        if (color) this.layaStatusTxt.color = color;
      }
    };

    // 3. Thực thi Skip Tân Thủ 0s sạch sẽ (chỉ tắt hướng dẫn tân thủ & mở khóa 6 Tab, KHÔNG mở rương/ghép mảnh)
    bot.cleanSkipTutorialNow = function() {
      var self = this;
      var nm = self.getNetMsg();
      self.autoSkipGuide = true;
      try {
        try {
          var ebObj = (typeof eb !== "undefined" && eb) ? eb : (typeof window !== "undefined" ? window.eb : null);
          if (ebObj && ebObj.getInstance) {
            var ebInst = ebObj.getInstance();
            if (ebInst && ebInst.inStage && ebInst.inStage() && ebInst.close) {
              ebInst.close();
            }
          }
        } catch (e) {}
        var atObj = (typeof at !== "undefined" && at) ? at : (typeof window !== "undefined" ? window.at : null);
        var zObj = (typeof z !== "undefined" && z) ? z : (typeof window !== "undefined" ? window.z : null);
        if (atObj) {
          try {
            var curGuideId = (atObj.data && atObj.data.id) ? atObj.data.id : ((atObj.guide && atObj.guide.data && atObj.guide.data.id) ? atObj.guide.data.id : 0);
            if (curGuideId && nm && nm.CG_GUIDE_STEP_FINISH) {
              nm.CG_GUIDE_STEP_FINISH(curGuideId);
            }
          } catch (e) {}
          try {
            atObj.data = null;
            if (atObj.guide && atObj.guide.close) atObj.guide.close();
          } catch (e) {}
        }

        var uhObj = (typeof uh !== "undefined" && uh) ? uh : (typeof window !== "undefined" ? window.uh : null);
        if (uhObj && uhObj.getInstance) {
          try {
            var uInst = uhObj.getInstance();
            if (uInst && uInst.inStage && uInst.inStage()) {
              var rName = (uInst.ui && uInst.ui.inputName && uInst.ui.inputName.text)
                ? uInst.ui.inputName.text
                : ("ThanhTon" + Math.floor(10000 + Math.random() * 89999));
              if (nm && nm.CG_ROLE_CHANGE_NAME_GUIDE) nm.CG_ROLE_CHANGE_NAME_GUIDE(rName, 0);
              if (atObj && atObj.check && zObj) atObj.check(zObj.CREATE_ROLE);
              uInst.close();
            }
          } catch (e) {}
        }

        try {
          var rDialog = (typeof R_ !== "undefined" && R_ && R_.getInstance) ? R_.getInstance() : (window.R_ && window.R_.getInstance ? window.R_.getInstance() : null);
          if (rDialog && rDialog.inStage && rDialog.inStage() && rDialog.close) rDialog.close();
        } catch (e) {}

        try {
          var gaCutscene = (typeof Ga !== "undefined" && Ga && Ga.getInstance) ? Ga.getInstance() : (window.Ga && window.Ga.getInstance ? window.Ga.getInstance() : null);
          if (gaCutscene && gaCutscene.inStage && gaCutscene.inStage() && gaCutscene.close) gaCutscene.close();
        } catch (e) {}

        try {
          var p0Obj = (typeof P0 !== "undefined" && P0) ? P0 : (typeof window !== "undefined" ? window.P0 : null);
          if (p0Obj && p0Obj.instance) {
            p0Obj.instance.guides = [];
            p0Obj.instance.step = 0;
            p0Obj.instance.substep = 0;
            if (p0Obj.instance.inStage && p0Obj.instance.inStage()) p0Obj.instance.close();
          }
        } catch (e) {}

        try {
          var deObj = (typeof De !== "undefined" && De) ? De : (typeof window !== "undefined" ? window.De : null);
          if (deObj && deObj.isInCombat) {
            deObj._pendingSkip = true;
            if (deObj.finishData) {
              deObj.endFlag = false;
              deObj.onEnd();
            }
          }
        } catch (e) {}

        if (nm) {
          if (nm.CG_ROLE_CHANGE_NAME_GUIDE && typeof H !== "undefined" && (!H.data || !H.data.name)) {
            try { nm.CG_ROLE_CHANGE_NAME_GUIDE("ThanhTon" + Math.floor(10000 + Math.random() * 89999), 0); } catch (e) {}
          }
          if (nm.CG_GUIDE_SKIP) {
            try { nm.CG_GUIDE_SKIP(1); nm.CG_GUIDE_SKIP(0); } catch (e) {}
          }
          if (nm.CG_HERO_VIEW) {
            try { nm.CG_HERO_VIEW(1002, 4, 1); nm.CG_HERO_VIEW(2004, 5, 1); } catch (e) {}
          }
          if (nm.CG_STOVE_JULING_GET) {
            try { nm.CG_STOVE_JULING_GET(); } catch (e) {}
          }
        }

        try {
          var riObj = (typeof Ri !== "undefined" && Ri) ? Ri : (typeof window !== "undefined" ? window.Ri : null);
          if (riObj && riObj.getInstance) {
            var yPanel = riObj.getInstance();
            yPanel.setGuideMode(false);
            yPanel._guide = false;
          }
          var btObj = (typeof bt !== "undefined" && bt) ? bt : (typeof window !== "undefined" ? window.bt : null);
          if (btObj && btObj.getInstance && !btObj.getInstance().index2Panel[0] && typeof ye !== "undefined") {
            var mb = btObj.getInstance();
            mb.register(btObj.TIANGONG, ye.getInstance());
            mb.register(btObj.HERO, si.getInstance());
            if (typeof Xa !== "undefined") mb.register(btObj.ASSISTAN, Xa.getInstance());
            mb.register(btObj.COPY, gb.getInstance());
            mb.register(btObj.JINGJI, fb.getInstance());
            mb.register(btObj.YOULI, riObj.getInstance());
          }
        } catch (e) {}
      } catch (e) {}
    };

    // Helper: Mở các Túi Quà / Rương Phúc Lợi trong Túi đồ để bung hết Vé Chiêu Mộ & Mảnh Tướng
    // (KHÔNG tự ghép mảnh tướng, KHÔNG quay gacha tiêu Ngọc!)
    bot.unpackGiftBoxesOnly = function() {
      var nm = this.getNetMsg();
      if (!nm) return;
      try {
        if (nm.CG_ITEM_USE_ONEKEY) {
          try { nm.CG_ITEM_USE_ONEKEY(); } catch (e) {}
        }
        if (typeof O !== "undefined" && O.bagDict) {
          var boxOneKeyIds = [];
          for (var idKey in O.bagDict) {
            var item = O.bagDict[idKey];
            if (!item || !item.id || !item.cnt || item.cnt <= 0) continue;
            // Bỏ qua mảnh tướng (để anh tự ghép tay)
            if (item.suipian && item.suipian.fullcnt > 0) continue;
            var op = item.opflag || 0;
            var isRandomOrAllBox = (op & (1 << 9)) || (op & (1 << 11));
            var isSelectBox = (op & (1 << 5)) && !isRandomOrAllBox;
            var isUsable = (op & (1 << 1)) || (op & (1 << 4));
            if (isRandomOrAllBox) {
              if (boxOneKeyIds.length < 10) boxOneKeyIds.push(item.id);
              if (nm.CG_ITEM_USE) {
                try { nm.CG_ITEM_USE(item.id, Math.min(50, item.cnt)); } catch (e) {}
              }
            } else if (!isSelectBox && isUsable && !item.panelID && item.mainType == 1) {
              if (nm.CG_ITEM_USE) {
                try { nm.CG_ITEM_USE(item.id, Math.min(50, item.cnt)); } catch (e) {}
              }
            }
          }
          if (boxOneKeyIds.length > 0 && nm.CG_BAG_BOX_ONEKEY_DO) {
            try { nm.CG_BAG_BOX_ONEKEY_DO(boxOneKeyIds); } catch (e) {}
          }
        }
      } catch (e) {}
    };

    // 4. Nút NHẬP GIFTCODE VIP (1-CHẠM): Nhập 38 Code với nhịp chuẩn 420ms/mã (chống Server Funtap nuốt code)
    // + Tự nhận Thư + Mở các Túi quà Phúc Lợi ra Vé & Mảnh (KHÔNG tự ghép tướng, KHÔNG tiêu Ngọc!)
    bot.startAutoGiftcode = function(btnRef, btnLbl) {
      var self = this;
      var lbl = btnLbl || this.gcPillTxt;
      var nm = this.getNetMsg();

      if (!nm || !nm.CG_CDK) {
        if (lbl) lbl.text = "❌ CHƯA KẾT NỐI";
        this.setManualStatus("⚠️ Chưa kết nối máy chủ! Hãy vào trong nhân vật trước.", "#EF4444", 4000);
        this.showToast("⚠️ Chưa kết nối máy chủ! Hãy vào trong game trước khi nhập Code.");
        setTimeout(function() { if (lbl) lbl.text = "NHẬP CODE 🎁"; }, 2500);
        return;
      }

      if (this._isRedeemingCodes) {
        this.showToast("⏳ Đang nhập Giftcode VIP, vui lòng đợi vài giây...");
        return;
      }
      this._isRedeemingCodes = true;

      var idx = 0;
      var total = this.giftcodes.length;
      if (lbl) lbl.text = "⏳ 1/" + total;
      this.setManualStatus("🎁 Đang nhập " + total + " Giftcode VIP (1/" + total + ")...", "#38BDF8", 16000);
      this.showToast("🎁 Bắt đầu nhập chuẩn " + total + " Giftcode (nhịp 420ms chống sót code)...");

      function nextCode() {
        if (idx >= total) {
          self._isRedeemingCodes = false;
          try {
            if (nm.CG_MAIL_QUERY) { nm.CG_MAIL_QUERY(1); nm.CG_MAIL_QUERY(2); }
            if (nm.CG_MAIL_ALL_GET) nm.CG_MAIL_ALL_GET();
          } catch (e) {}

          setTimeout(function() {
            try {
              if (nm.CG_MAIL_QUERY) { nm.CG_MAIL_QUERY(1); nm.CG_MAIL_QUERY(2); }
              if (nm.CG_MAIL_ALL_GET) nm.CG_MAIL_ALL_GET();
              self.unpackGiftBoxesOnly();
            } catch (e) {}
          }, 800);

          setTimeout(function() {
            try {
              if (nm.CG_MAIL_ALL_GET) nm.CG_MAIL_ALL_GET();
              self.unpackGiftBoxesOnly();
            } catch (e) {}
            self.showToast("✅ Đã nhập đủ " + total + " Giftcode, Nhận Thư & Bung Túi Quà ra Vé + Mảnh! Anh vào ghép tướng nhé!");
          }, 1800);

          if (lbl) lbl.text = "✅ XONG " + total + " CODE!";
          self.setManualStatus("● Đã nhập đủ " + total + " Code, Nhận Thư & Bung Túi Quà ra Vé + Mảnh!", "#10B981", 6000);
          setTimeout(function() {
            if (lbl) lbl.text = "NHẬP CODE 🎁";
            self.updateHud();
          }, 3500);
          return;
        }

        var code = String(self.giftcodes[idx] || "").trim();
        idx++;
        try { if (code) nm.CG_CDK(code); } catch (e) {}
        if (lbl) lbl.text = "⏳ " + idx + "/" + total;
        self.setManualStatus("🎁 Đang gửi mã (" + idx + "/" + total + "): " + code, "#38BDF8", 4000);
        setTimeout(nextCode, 550);
      }

      nextCode();
    };

    // 5. Nút SKIP TÂN THỦ 0s: Chỉ Skip Tân Thủ & Mở khóa 6 Tab giao diện (KHÔNG tự mở rương hay ghép mảnh!)
    bot.startSkipGuide = function(btnRef, btnLbl) {
      var self = this;
      var lbl = btnLbl || this.sgPillTxt;

      if (lbl) lbl.text = "⏳ ĐANG SKIP...";
      this.setManualStatus("🚀 Đang Skip Tân Thủ 0s & Mở khóa toàn bộ giao diện...", "#FB7185", 5000);
      this.showToast("🚀 Đang Skip Tân Thủ 0s & Mở khóa 6 Tab giao diện!");

      this.cleanSkipTutorialNow();

      setTimeout(function() {
        self.cleanSkipTutorialNow();
        if (lbl) lbl.text = "✅ ĐÃ SKIP!";
        self.setManualStatus("● Đã Skip Tân Thủ 0s & Mở khóa toàn bộ 6 Tab chính!", "#10B981", 5000);
        self.showToast("✅ Đã Skip Tân Thủ 0s & Mở khóa toàn bộ 6 Tab chính!");
        setTimeout(function() {
          if (lbl) lbl.text = "SKIP TÂN THỦ 🚀";
          self.updateHud();
        }, 3000);
      }, 600);
    };

    bot.beforeConnectHook = function(url, acc) {
      try {
        if (typeof p !== "undefined" && p.ACCOUNT) {
          var rawAcc = String(p.ACCOUNT);
          var sid = p.GLOBAL_SERVER_ID ? String(p.GLOBAL_SERVER_ID) : "";
          if (sid && rawAcc.indexOf(sid + "-") !== 0 && String(acc || "").indexOf(sid + "-") !== 0) {
            acc = sid + "-" + rawAcc;
          } else if (!acc || String(acc).indexOf("undefined") >= 0) {
            acc = (sid ? sid + "-" : "") + rawAcc;
          }
        }
      } catch (e) {}
      return { url: url, acc: acc };
    };

    bot.onHumanInfoLoaded = function() {
      try {
        if (typeof we !== "undefined" && we.sendLogin2php && typeof p !== "undefined" && p.GLOBAL_SERVER_ID) {
          we.sendLogin2php(p.GLOBAL_SERVER_ID);
        }
      } catch (e) {}
      this.updateHud();
    };

    // Enforce upright Portrait Mode (Màn Dọc) & prevent Guide overlay from blocking mouse clicks on Web
    try {
      if (typeof window !== "undefined" && window.DAUTO_FORCE_PORTRAIT && typeof Laya !== "undefined" && Laya.stage) {
        Laya.stage.screenMode = "none";
        Laya.stage.canvasRotation = false;
      }
      var unlockGuideBlocker = function() {
        try {
          var atObj = (typeof at !== "undefined" && at) ? at : (typeof window !== "undefined" ? window.at : null);
          if (atObj) {
            atObj.isLock = function() { return false; };
            if (atObj.guide) {
              atObj.guide.mouseEnabled = false;
              atObj.guide.mouseThrough = true;
              if (atObj.guide.maskArea) atObj.guide.maskArea.mouseEnabled = false;
            }
          }
        } catch (e) {}
      };
      unlockGuideBlocker();
      if (!bot._guideUnlockTimer) {
        bot._guideUnlockTimer = setInterval(unlockGuideBlocker, 400);
      }
    } catch (e) {}

    bot.onHeroAcquiredCheck = function() {
      return;
    };

    // 9. AUTO QUÉT ĐẤU TRƯỜNG (ARENA JJC) + MUA CHỢ ĐEN BẰNG BẠC + TRÙNG SINH TƯỚNG PHỤ
    bot.startAutoArena = function(useTickets) {
      var nm = this.getNetMsg();
      if (!nm || !nm.CG_PANEL_OPEN) return;
      this._isAutoArena = true;
      this._arenaUseTickets = !!useTickets;
      this._arenaRefreshTries = 0;
      this._arenaFightsDone = 0;
      try { nm.CG_PANEL_OPEN(1013, ""); } catch (e) {}
    };

    bot.onArenaQuery = function(d, b, f) {
      var self = this;
      var nm = this.getNetMsg();
      if (!nm || !d) return;
      try {
        if (f && f.length && nm.CG_JJC_BOARD_MOBAI) {
          for (var r = 0; r < f.length; r++) {
            if (f[r] && f[r].roleBase && f[r].roleBase.uuid && f[r].isMobai === 0) {
              try { nm.CG_JJC_BOARD_MOBAI(f[r].roleBase.uuid); } catch (e) {}
            }
          }
        }
        if (d.isQuick === 0 && (!d.quickTip || d.quickTip.length === 0) && nm.CG_JJC_SET_QUICK) {
          try { nm.CG_JJC_SET_QUICK(1); } catch (e) {}
        }
        if (d.boxList && d.boxList.length && nm.CG_JJC_BOX_GET) {
          for (var bx = 0; bx < d.boxList.length; bx++) {
            if (d.boxList[bx] && d.boxList[bx].state === 1) {
              try { nm.CG_JJC_BOX_GET(); } catch (e) {}
            }
          }
        }
        if (d.isChengJiuRed && nm.CG_JJC_CHENGJIU_REWARD_QUERY) {
          try { nm.CG_JJC_CHENGJIU_REWARD_QUERY(); } catch (e) {}
        }
        if (!this._isAutoArena) return;

        var freeLeft = d.leftFreeCnt || 0;
        var ticketCnt = (d.fightItem && d.fightItem.id && typeof O !== "undefined" && O.getCountByID)
          ? (O.getCountByID(d.fightItem.id) || 0) : 0;
        var canFight = (freeLeft > 0) || (this._arenaUseTickets && ticketCnt > 0 && this._arenaFightsDone < 5);

        if (!canFight || !b || !b.length) {
          this._isAutoArena = false;
          if (this._arenaFightsDone > 0) {
            this.showToast("⚔️ Đã tự động quét thắng " + this._arenaFightsDone + " trận Đấu Trường (Chọn đối thủ yếu nhất)!");
          }
          return;
        }
        if (typeof De !== "undefined" && De.isInCombat) return;

        var opps = b.slice().filter(function(o) { return o && o.roleBase && o.roleBase.uuid; });
        opps.sort(function(x, y) {
          return (x.roleBase.zhandouli || 0) - (y.roleBase.zhandouli || 0);
        });
        if (!opps.length) {
          this._isAutoArena = false;
          return;
        }

        var weakest = opps[0];
        var myPower = d.myZhandouli || 0;
        var oppPower = weakest.roleBase.zhandouli || 0;

        if (myPower > 0 && oppPower > myPower * 1.15 && this._arenaRefreshTries < 2 && nm.CG_JJC_TARGET_REFRESH) {
          this._arenaRefreshTries++;
          setTimeout(function() {
            try { nm.CG_JJC_TARGET_REFRESH(); } catch (e) {}
          }, 300);
          return;
        }

        this._arenaRefreshTries = 0;
        this._arenaFightsDone = (this._arenaFightsDone || 0) + 1;
        var targetUuid = weakest.roleBase.uuid;
        setTimeout(function() {
          try {
            if (typeof _t !== "undefined") {
              _t.combatData = null;
              _t.backstage = false;
            }
            if (typeof Et !== "undefined" && Et.show) {
              Et.show(9, targetUuid);
            } else if (nm.CG_COMBAT_READY) {
              nm.CG_COMBAT_READY(9, targetUuid, 0, 0);
            }
          } catch (e) {}
        }, 350);
      } catch (e) {}
    };

    bot.onArenaChengjiuQuery = function(list) {
      var nm = this.getNetMsg();
      if (!nm || !nm.CG_JJC_CHENGJIU_REWARD_GET || !list || !list.length) return;
      for (var i = 0; i < list.length; i++) {
        if (list[i] && list[i].state === 1) {
          try { nm.CG_JJC_CHENGJIU_REWARD_GET(list[i].id); } catch (e) {}
        }
      }
    };

    bot.onArenaFightFinished = function(result) {
      var self = this;
      if (!this._isAutoArena) return;
      setTimeout(function() {
        try {
          var nm = self.getNetMsg();
          if (nm && nm.CG_PANEL_OPEN) nm.CG_PANEL_OPEN(1013, "");
        } catch (e) {}
      }, 450);
    };

    bot.onShopQuery = function(shopInfo, goodsList, refreshItem, nextRefreshTime, freeCnt) {
      var nm = this.getNetMsg();
      if (!nm || !shopInfo || !goodsList || !this._isAutoShop) return;
      try {
        var sType = shopInfo.shopType;
        for (var i = 0; i < goodsList.length; i++) {
          var g = goodsList[i];
          if (!g || !g.itemData || !g.needItem) continue;
          if (g.openDesc && g.openDesc !== "") continue;
          if (g.limitBuy !== 0 && g.nowBuy >= g.maxCanBuy) continue;
          if (g.needItem.id === 101) {
            var mySilver = (typeof O !== "undefined" && O.getCountByID) ? (O.getCountByID(101) || 0) : 0;
            var remCanBuy = (g.limitBuy === 0) ? 1 : Math.max(1, (g.maxCanBuy || 1) - (g.nowBuy || 0));
            if (mySilver >= (g.needItem.cnt || 0) * remCanBuy && nm.CG_SHOP_BUY) {
              try { nm.CG_SHOP_BUY(sType, g.itemData.id, g.itemIndex, remCanBuy); } catch (e) {}
            }
          }
        }
        if (freeCnt > 0 && this._shopFreeRefreshCount < 3 && nm.CG_SHOP_REFRESH) {
          this._shopFreeRefreshCount = (this._shopFreeRefreshCount || 0) + 1;
          setTimeout(function() {
            try { nm.CG_SHOP_REFRESH(sType); } catch (e) {}
          }, 400);
        } else {
          this._isAutoShop = false;
        }
      } catch (e) {
        this._isAutoShop = false;
      }
    };

    bot.rebirthFodderHeroesForMainTeam = function() {
      var nm = this.getNetMsg();
      if (!nm || !nm.CG_HERO_CHONGSHENG) return 0;
      try {
        var all = (typeof tt !== "undefined" && tt.heros) ? tt.heros.slice() : [];
        if (all.length <= 6) return 0;
        var top6 = this.getTopMetaHeroes(6);
        var topMap = {};
        for (var i = 0; i < top6.length; i++) {
          if (top6[i] && top6[i].heroUuid) topMap[top6[i].heroUuid] = true;
        }
        var rebirthed = 0;
        for (var j = 0; j < all.length; j++) {
          var h = all[j];
          if (h && h.heroUuid && !topMap[h.heroUuid] && (h.lv || 1) > 1) {
            this._isAutoRebirth = true;
            try {
              nm.CG_HERO_CHONGSHENG(h.heroUuid);
              rebirthed++;
            } catch (e) {}
          }
        }
        if (rebirthed > 0) {
          var self = this;
          setTimeout(function() { self._isAutoRebirth = false; }, 1500);
        }
        return rebirthed;
      } catch (e) {
        return 0;
      }
    };

    bot.version = "7.9";
    if (bot.layaBtnSub) {
      try { bot.layaBtnSub.text = "PRO v7.9 • S2"; } catch (e) {}
    }
    bot.updateHud();
    console.log("[D-AUTO v7.9] Đã cập nhật chuẩn 27 Giftcode thật • Nhịp 550ms/mã chống sót code!");
  }

  attachCleanRerollPlugin();
})();
