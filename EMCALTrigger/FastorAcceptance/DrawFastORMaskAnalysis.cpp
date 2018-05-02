#ifndef __CLING__
#include <algorithm>
#include <array>
#include <bitset>
#include <functional>
#include <fstream>
#include <iostream>
#include <memory>
#include <vector>

#include <ROOT/TSeq.hxx>
#include <TBox.h>
#include <TCanvas.h>
#include <TFile.h>
#include <TH1.h>
#include <TLine.h>

#include "AliCDBEntry.h"
#include "AliCDBManager.h"
#include "AliEMCALGeometry.h"
#include "AliEMCALTriggerDCSConfig.h"
#include "AliEMCALTriggerTRUDCSConfig.h"
#endif

using Range = ROOT::TSeqI;
using TFilePtr = std::unique_ptr<TFile>;

AliEMCALGeometry *egeo(nullptr);

int GetTRUChannelRun2(int ifield, int ibit){
      const int kChannelMap[6][16] = {{ 8, 9,10,11,20,21,22,23,32,33,34,35,44,45,46,47},   // Channels in mask0
                                      {56,57,58,59,68,69,70,71,80,81,82,83,92,93,94,95},   // Channels in mask1
                                      { 4, 5, 6, 7,16,17,18,19,28,29,30,31,40,41,42,43},   // Channels in mask2
                                      {52,53,54,55,64,65,66,67,76,77,78,79,88,89,90,91},   // Channels in mask3
                                      { 0, 1, 2, 3,12,13,14,15,24,25,26,27,36,37,38,39},   // Channels in mask4
                                      {48,49,50,51,60,61,62,63,72,73,74,75,84,85,86,87}};  // Channels in mask5
      return kChannelMap[ifield][ibit];
}

int RemapTRUIndex(int itru) {
  int map[46] = {0,1,2,5,4,3,6,7,8,11,10,9,12,13,14,17,16,15,18,19,20,23,22,21,24,25,26,29,28,27,30,31,32,33,37,36,38,39,43,42,44,45,49,48,50,51};
  return map[itru];
}

std::vector<int> ReadMaskedFastors(const char *textfile){
  std::vector<int> fastorabsids;
  std::ifstream reader(textfile);
  std::string tmp;
  while(getline(reader, tmp)) fastorabsids.push_back(std::stoi(tmp));
  std::sort(fastorabsids.begin(), fastorabsids.end(), std::less<int>());
  return fastorabsids;
}

TCanvas *PlotMaskedChannels(const std::vector<int> &deadchannels){
  // first three helper functions to draw the
  // of course in functional style (lambda functions)
  std::function<void()> DrawSupermoduleGrid = [](){
    TLine *l(nullptr);
    // EMCAL
    for(int i = 12; i <= 60; i += 12) {
      l = new TLine(0, i, 48, i);
      l->SetLineWidth(2);
      l->Draw();
    }
    l = new TLine(24, 0, 24, 64);
    l->SetLineWidth(2);
    l->Draw();
    l = new TLine(0, 64, 48, 64);
    l->SetLineWidth(2);
    l->Draw();
    //DCAL
    for(int i = 76; i < 100; i+=12){
      l = new TLine(0, i, 16, i);
      l->SetLineWidth(2);
      l->Draw();
      l = new TLine(32, i, 48, i);
      l->SetLineWidth(2);
      l->Draw();
    }
    l = new TLine(16, 64, 16, 100);
    l->SetLineWidth(2);
    l->Draw();
    l = new TLine(32, 64, 32, 100);
    l->SetLineWidth(2);
    l->Draw();
    l = new TLine(0, 100, 48, 100);
    l->SetLineWidth(2);
    l->Draw();
    l = new TLine(24, 100, 24, 104);
    l->SetLineWidth(2);
    l->Draw();
  };

  std::function<void()> DrawTRUGrid = [](){
    TLine *l(nullptr);
    // EMCAL
    for(int r = 0; r < 60; r += 12) {
      for(int c = 0; c < 48;  c += 8 ){
        if(c == 0 || c == 24) continue;
        l = new TLine(c, r, c, r + 12);
        l->SetLineWidth(1);
        l->SetLineStyle(2);
        l->Draw();
      }
    }
    // DCAL
    std::array<int, 2> colsdcal = {{8, 40}};
    for(int r = 64; r < 100; r += 12){
      for(auto c : colsdcal) {
        l = new TLine(c, r, c, r + 12);
        l->SetLineWidth(1);
        l->SetLineStyle(2);
        l->Draw();
      }
    }
  };

  std::function<void(int, int)> DrawFastOr = [](int col, int row){
    TBox *result = new TBox(col, row, col+1, row+1);
    result->SetLineWidth(0);
    result->SetFillColor(kRed);
    result->Draw();
  };

  TCanvas *result = new TCanvas("maskedFastorGrid", "Masked Fastors", 800, 600);
  result->cd();

  TH1 *axis = new TH1F("axis", "Masked FastORs; col; row", 48, 0., 48.);
  axis->SetStats(false);
  axis->SetDirectory(nullptr);
  axis->GetYaxis()->SetRangeUser(0, 104);
  axis->Draw("axis");

  DrawSupermoduleGrid();
  DrawTRUGrid();

  int col(-1), row(-1);
  for(auto d : deadchannels){
    egeo->GetTriggerMapping()->GetPositionInEMCALFromAbsFastORIndex(d, col, row);
    DrawFastOr(col, row);
  }
  return result;
}

void SaveCanvas(const std::string &basename, const TCanvas *plot){
  std::vector<std::string> endings = {"eps", "pdf", "png", "jpeg", "gif"};
  for(auto e : endings) plot->SaveAs(Form("%s.%s", basename.c_str(), e.c_str()));
}

void DrawFastORMaskAnalysis(int runnumber, const char *textfile){
  egeo = AliEMCALGeometry::GetInstanceFromRunNumber(runnumber);
  std::string textfilestring(textfile);
  SaveCanvas(Form("posMaskedFastorsAnalysis_%d_%s", runnumber, textfilestring.substr(0, textfilestring.find(".txt")).data()), PlotMaskedChannels(ReadMaskedFastors(textfile)));
}
