
# ==========================
# ObfuXtreme v4 Loader
# ==========================

import sys
import base64
import marshal
import zlib

# ---- Dependency guard ----
try:
    from Crypto.Cipher import AES
    from Crypto.Util.Padding import unpad
except ModuleNotFoundError:
    print("[FATAL] Missing dependency: pycryptodome")
    print("Install with: python -m pip install pycryptodome")
    sys.exit(1)

# ---- Python version guard (AUTO) ----
EXPECTED_PY = (3, 12)

if sys.version_info[:2] != EXPECTED_PY:
    print("[FATAL] Unsupported Python version")
    print(f"Expected: {EXPECTED_PY[0]}.{EXPECTED_PY[1]}")
    print(f"Found:    {sys.version_info[0]}.{sys.version_info[1]}")
    sys.exit(1)

def _xor(parts):
    from functools import reduce
    return reduce(lambda a,b: bytes(x^y for x,y in zip(a,b)), parts)

_KEY = _xor([b'\x1dR\xc8vOl\xf5\xd0\x90\x9c\xad\xde\xba\xeb\xcdf\xec\xe9I\xbf\xe2[D/\xb7H\x1a\xf02P\x84y', b'\xb3\x89\xfaU\x0e\xa0\x1d\xe2\xfek\xa2\xd9\xfa<b\xe8}\xb3\xe6\xd8fy\x0c\xd3\xdc\xf1\xc5\xb0\xacG@<', b'Y\xd8\xc6nt\x9aa\x03"\xec#\xc7\x8a\xf8\x9a\x92\xfe\x99\x0e\xc9O\xc6]\xeb\xd4\xfa\x86\xb6\x07\xd0Nb'])
_IV  = _xor([b'\xa7Gh\x8a`\x80p|}x\n\xddH\x87\x9a4', b'Y\xe2\x1b\x90<\xbds{\xa7\xabx\xee\x9b\xf4\xe5v'])

def _decrypt_str(d):
    iv, p = d[:16], d[16:]
    return unpad(AES.new(_KEY, AES.MODE_CBC, iv).decrypt(p), 16).decode("utf-8", "ignore")

def _decrypt_bytes(d):
    iv, p = d[:16], d[16:]
    return unpad(AES.new(_KEY, AES.MODE_CBC, iv).decrypt(p), 16)

_enc = base64.b85decode('PmxCgwpPQ@!3SEmL6CpvAu*^A;nqIT`+vs3H%pdx;c)`7H0-Se$4a5sX#-~E-Wy4b(8}Wq^2o;vaq&J;-t|@yNQyb4HzkH8T92Q=e@uZ#k9nnI&R!v54B_iF>zvRtldm6J@u9-f3_Ms#gxp_I7snRK8Q&ttH1BFzy_YjK#%_Z1Kkvss!vbn{o8^U_!3lua>QzURXWXeCU%V<o@59Is*mW7EV~md*-Tsl?Wa0aN9>2X6&_7ypgG}<@vU4ow#a$QdVEg(MaIQ%?OOvUDEn{g!Bh}=O`WiNXGf5aIQ6P?lY+_rEcmF-L#MX1P*p2TUr(X#&KfedkM!iP@`S{|Ye$WmKx8X(_DGi*AjJh5X*~|gw&eb@9^hyOmuXgi5(4Yc|4YO~F7mxI0IX)~>6PuTHIyArRp(VWaSva{-tps#fBpU-{A6tGYrxbbPt7fSE{txQvhKIc@V8K?Dbkavky}@o32I8sIga?Z@D%m(U2?Ab><vC($W`m02umdrQBW~q01F9ny4R=8mujW|?shV+RMd8KB$gd?^48e6+9z-tPrzT!OMJSEKDeC+w17bhQH{3^^C2vT=nR<|Xt8Ew3wj&VxN>UONgQBANDqLO%3zR7*oL(!pnf*I#>;SkeZx%4}s2#H&^tHI;XN5j<^yRkF{h18n&JAec;X6%5=^5WjHIn*^c$yQ)8)CdfN4}=y{j(+RjMuzOw-lkXrbfx@zjMv4KR)fHvvdX>jipDFGBnWR-GPWy$gava!jR#G?y1Z|1Fsd@zt~DLlQ5^mRt^X|=H~!7S)Yk3)Q?5XJ!g2c*d^+AL-p=G(IJqSsx=$M09~q=I0HZ`BPzg5rv{k*uQe(j7Nk-M=?<R1&u*q?Rb@P-DlfggjW4%Yh}K_UFH`JW@@4VyM?FR@HBgXoJS0iT+L?u4w=UR3s)Q2Xp-|gw-2v61ITQ9<5!~IEb187Z^Yvb5GS|r~Bo)CRQAj7`++<J|>SfKM3V8>iKxMXgRZqudui(Bww@Tt*JHxr?RWeA4`q+_T$0IdTS_lVQ>0UJzNWJeDg;ZGgruEb9Zp?krM#MH9=Dea*Nbu=^!=qQOkK&QI8xo7qlddZEIma#m3WxxT4UEy^-bA|V+dLh(Rd$_(`WA5N4{w;(Cw#X6@xS{r-Q6g=+pxMuCyjN7OMQJZ{704PdW0l>jTsMKq7gMdMv?)hTFIt39Ve0Mtu{y%N5BEN@rE-ibty}h5)>_UJ7}%eFtPq3B!$X(+2g+#5QA>>;`(v}_@XC2J6$Kn^8{RRaH#kXN^;wp^k?LzUKCMy8-b$pB;&JqobpW9Q<vyH+KIHiUS;lY16@h1k2woJ@SnKjUefX;NxxOT)75Qzv(S?coxhUccV7l~VlR6w4kZmWF^{1#VeTtUZr{8K9yiaIt#lj_ELB|K*y{<9;cTang$Qn(!aD|BoPbsw45A+to^D~Wmnle4XbX^!kA2ZxOa6Zc&G8S$ob(iW#gN^JYmnPuKQ)|k{BI~DHm}A~B3Vgx(eGDO2{RbZcU+z{ikd<}`gEdX^(*xDWG3$ax#rCRdC?H|G}W;3Z7CJy7c8PduMCfLVssOtzbUsk8nPF%m}IIKX-?oS;=dlPm!^*fY5s>u_<O~-Qy9D8@|qA!DU3Ivg!ddrTxAB1b-qT{@k~#;3p_mk48G~{W06+De$%WKyG{DPV$IGA1yf#3bXyND-i1*L@3i|pxK}fmlBlKTJ@ftgXsMkXN>U-LbuhXgd}=<i0|dAz09mL+SG^q|=XlE-sMkzJChT=LQiV39iArCxEYjMIn0@#&h@C7S@Kgu&o-UBbvfF((TN~<O(6!r|R@uis&Ev>qw-gEIC3;xOhPQJgD;%}(MWhx(uIJ(4YEG0*nR^b@`#KHlL}SRtQUD1$3;8o9$q#_{pu~E!%)(v!sWB!jGoG<e&au%l$yx9F$kChCYaHB23yZ!T9&lu8`Otp$yYOW)j}GXAVN$w;&Cr1FG=gg<Zc6%ZA|4gTNDK2h-3Yxlw<+!z7c1~tU#oRBj10y*W{BOJJse}@S;uZZFgWJ1WA-bVDXhfPVHxcEnDj=hc2+i1mLds2`KZATSw-_f{mQtuOl49**G$5o>X=gtu$Dq&F@`Sdd|RDOCIgx>DQ@auP|gVBg(^I>x?fEFLYi^n)6Sd}8%RKmp-qp9V>*w0stfb(^5Y#V!4R%M8=-+C41KCyJaM3eAnJEVYTsqRtF*t{*4zZ<c$g=FB4@pX+hbXn8e8AG1g%M)l{Fwe#}V`O$A<=^ZjH_&H`MGj&)MwU{miFe3l09Ps_PbQVqDkm(VQ>$w>5T!Hf>lC;zgLT6)>WRLR4f~91SKXnNxYt3jwqsT_@X2)vC$Pjpw|VgF9=A_M=TY2_JFWR#_R^tWMyVr5`ZdXTp`G6zMQS?38c`)g%5Uth&db7Ja_P0&cR&_P4iw)xlA1WRM?a@*O-ae;lSjJXq|!5Dr{$!HB};nvw;+)@D{-wQYOzjnxO-)BxvD<FYVfM&f4#OrBC#oOlrm^l)`SwZai(XjceLF;bOuXSSA0zl(;LX=Y=1Vc88B=NgCkT`jsAhG{LYTJmF=`31VK3v0V@+VbAL*QSXj*4uW?3dU5DPq$%QzaVJf1C4_|yn8VQ(;+V^aSt5pCVeuFZ({2wGhJtjl5(#<2H2NH$VxYltanEua~T_8(L3wvxkZZL$$ojy^S6d+9HnqQBgU)}^QKMTDX1=xC*rFa0w84fb4Wchk6E5S84NeX#_b2Qw4ewxlC6y4=le<91KMQv2US{2y^F`kfFA&{a7i8(!#@d3#^ng9Mxf2x!<KEldgfK)=Z9a3rIXd?=tn(?n}f#Wlh}>e6&t6`-zVXiGl5_HH~qJ{0T&p#W#%eI)X~8ID)G_`AH6H)oWi}U4k%Q!s09sy0W@S~s>3hKuw8x+c+<p10m295u$0u?$;|GUQ0NGmRUpdx5q=0WmW0<Dxi$2re~R*QHXc3g78R_`#IFn-7#h*o&O<14Wb*_GD9;FkGdGWW%!6QAAX*zYW=&j+GkgNiw#5ZOiEfqkq^l{IrcuDs<N`O7_-I4M?^(<-;)aEGqhYwPY-~INOSN%|A)WY&-BmKdK#4>{Tij&0^RgycAB#2wwcSN3f)cf4W}u6T1vO?Yw?5%tp9_SbU(7B0tNqNt{3Z7O%|Ld{(?4FiXRiOY3Jc4{UTw6upN6)2<ypd7kOsnYI!i7bAoPiDDQ1WZVq*}j0<I)#iQe&-xdYG01Dwv}GPjHI>p&>1(3Goir47keG0(slZy5NbrJznUF65wb{^*6?$&%HZP9DM3xR~AOxnV*E?@Dt{)@Ch&!=HwAL{zuOcg)ln^gV{WDL^>Xh7Im(eAO7%c$oj>>15-J8as#XA2DNj4Mz^2AM(nq1dIi{8mi~)`x~L$R!`qK2e1ax_Ksfs01l7w@wcdxlMvo3AS!JyRCkFJKhokVk7CBo$UT26z>Cd5d*!Flp66MhCd7tU6PL!h(b3|)DaQe;IOBf>hbrXCA{K=|;%a%cDr{@DF%A`4;;P%Do7@m=MGB02Kw>yTrkey`w@e|ud+baM@jd;qJ6IfzCNgWNHan9+f{G@$mCD%Z7CS)v_XPc5M)vyAaj~<JPGVIbLdJJn(F0LgV;+zO^}7Fj9jj6h+mGz()D98PKiPVS#tJ7muln{hOMkId8w*@+<Rj1VE*u@4MGJTi$Ki(<Cq7!mWIqO}irxi|P&zjnU3D23zZ%`CO2jy_g0h9$DC&*h#kn+Bb<PvMDN<L_SXNlCCndbzSkm2Iw~jT2>2euDd;^cMIBo9-azR-7Z_0Z|tewW`S;j9XTXV|zj~OY%<sdqq{66js6<C)=934i(z`4Sh-pu@hU0^+E7ytAx8%ISZVV7ZxvCAi9lSm-1ABN(6x(^=Lf?O~__8$v*vgPxaBui|{(@IrkJ6Z-2`ORRYLBiF(!hjGSHW&MWH;SRMQ)#nketK0cw>thugU<(YCC~%k$fyZid7tT~hweCxFa&p>2W@WYf-z&cIVe9FSxZ?Nh=>7TscNFlotf448t$pXSQ&tl-RFXRH9XkAlopZkH0{XAMqf!gERka|!j;jBy`+q3aYF?o2qE80j|j8s_Fr+U*<_*@D|aLDYr5EL$i#pOMzQuLw#+Ua6_RV7vQ1l`qFVC(j6rlVCBh-ig5p@UJOXarEE^y!^f0k!Fk4oQqRoh+;AMb<X{@daWwezLyX)RQ(23etUb-P+>Tmba3$rW3+`ohWmjVsUQ1XW3b(QwYnXgz1{5<Vn{95fCAcrV)gDXKT{+cozX2DpX__5f$iEmt+vBd3I@Utp|BQ!a^KJK(zH!6-KT@M2bDD1JNXkegApHyPHzZ1qoO@H%sVcT1*CyQMCKp`|)-#*+AYpM712Mro2%>t3`T?XXWK24Xq9@6)15^iQtc`^rGBeELfDn!5<6muvmb-3ujL)~rPBbD#Rc1wvQ1T@VVQF`29_IjB#K?UE7{zU)fjhwp7uNj3;k=X~bZId<mktdX$t+wPovH7R{Q~g0^CD3yV%2+)YZ#1^$nVj0I>TadlE?tO}`1@&(wvrJ<xk|egFF4^#@@nE6rU=L3Vg2YqoU>YET+)6S=_~-MC$~sD)jgT*uYm@F-@ifLzv^bN`3KXn8Sl3O>Q=f<Y?4ehD%Ia|8`sD_ggpZCrbqgV@#ON@VmD`nkX-^pY_ZH-t<eHPPlQaAPmUnTZ*Of>b>E8VcHv67hkk;2_2gytBXPsB%80(o_4>pKc8H^jypAB2_#+%eZ89IkF^3a_#f?Jb@UvR4&SrK9k3>B>u+EUE1`0H2V3rY@9x5^svHgRBTOJ{&4Ru{@&zFY%*5S=T--4N2@nm%)$*6YSD-W|$Eu4$ceahFj&~ccf3<8K#RnH1Yau`4YSi`+-R&G-SWc%xlNX^5wl33<l>7lG!@F?=}D+PGQ@>sl3^$@WFmt9`~45@MgBc+IH%#NQA)J(w~Dc18`j7LEN)*x5%ILjO5Ggslo+5rOf6XgOgGY1EuwxO$<Tlg@CSF+XNF)Dd_TKgo2S*v*^A65_c>6oUKRIRiB`MwP_(y9GT4KkmV40&~aH-$U0)l80T?0lEVbsq?j121{Mj+P#5qIMjB17R3D_=|LY^$ZBGTg<V6BhofnTK?nLpzEQt3>>l?bZ5MPC;N-QJhftW5NQZaBx9rn{x$g7b?o_fTRdfRw<x;b;0pU>@De@hVvfM3jg89ik(|&o9*QT@I91HYc+KlF%#;26?X^j?e(T6Z$dJpG8=g$0M2KrKK5PL(wCzL>iYMs;+61^hd8t|iardXl10ciUuJ=)ymA0w6kp$p^>{IJ`n81TR%XI9(9i0y?nX_xQ%a#mQwgY$8>6wq(S5$oZH|6n8b-$*T6WF`qV%^=VH7|gdUXS6zo>_3uU5z9zg4bOA5P=-DROe*E2j(DyJGy+MK;H|Xczxu`*DRM6nB<6Q6j<|YK9_>ld$b;LSnJC9w!4Xw@4R&O-j`(mdWtc+hBSOcXyMo+bQMu#@1$zTYsciWMGrrT*q}d^&BBl*ZRv7{O%OJm>O)~FnQ2G(Z??^iFelIMOVM0QKKfQlv_mq}ByWxng(I|#S(2}$kaJf0x>KGXkVwQq4jiP{+jq&WLj7AGughb2T%Awb6Ow`q!ThrT=XsgwVuXgK^=7rEpipEm5%G+d%XDt$Ji80@wTb-!ku9_bZvm2X%6r=_H>O>3=3r;_z>5qhrsA9Ed2~JcB`)!}DF&0u|3nD}Jhjfxda4*%HK=qt?jo9=*J0(!DGf5^@)eX~$^~nVMLZjb_E;{_4qT6431bu=P%_neGmFI!Hr8x6tJuN06qPxD=nuSqM#TS;$RFICNkK3opYC{?#tllefLe|+-s%nIsRKp*+Y4bb-3^Ul`3PK{YOTu540TEXAqf`fb?|v2F3!?1i+@H;ev_;Kq4Z1KYpnhfTJgqbxPU7|`{^(^3ih<<W<36sfL*MzSIi-b@1UsWMjQk;7rPdmSZPG6_$X1_s>Nq(n@d{Kq{gDu!h~nlmJ9g54x4%M0q;jwny%6|{<T}np0!y7a$*Ki%nUT~iXj~w-i}i+inX95wVe272g+B1`MXHW*2cE58FqkF94efSF-rkaIMK_Xnyj#ZS-_z@yF8tswzd9D%?I!Bf7ylE@?(%rm;m>lVcH*##Gdly5ZVrsB0*X~FgWDFP4&vzBVnh?_I0iQXk#f0J*j3(|I~@Hk%l<<wQa09=FMm>dLP*=3_=s-YX09|oD_b8-E4LSraAu-QJCPbOZ)}TMx-7K509c=^pe;fX3i&w`EoowoIM45ond?i8Kzf#LclSo0XFz-1$ueMAzBgV8a1(KffbDQvh5Jj)IwMbp6PHwT3c(`;r-EE32mAAy^?a9nNO7Tokj%`G|`Lc_GwfJ$Ii7E_I<`JGz9v`9xij;3WJgpY_QE@!vj7lCOh{;EWzAvFh%qQGBOI8FMqg8y6}~OXM@AQRUA-hsHs4e9F5D?>sjK+&$e4grYb7vX33%;Ed+C{<I}4yi`7qfG~2(hC%?HN^`)$bAH`!B(Q$4@q$7@SiZP<x%z3bDpAr<cl9bXH3J^m2MN8h_UN^g#)nu(GbpoW3?b*$vPxr$Y6gHxnBbQN{0K^{m-b8#F$xf;slAlZv6hmptxK$rV`SbnPwIffjfr$ldGU^fa>g07YySXn`2xA3<?50^w7hp?7RfV+1gUMf1tH3#sLG5oqRS}}oi^VaHeS%7IJgDquU}sQon38crf@o_*T~*&g9E-jznUKrUAuRM$*K<O`+Q!G~pR)j#2D94VpPeCvEJmCbywyAllyN|qnn@ie`-fRj$*=kQ{=O)S7cA7KJ)u|O_Abc7j(`-_k#34O%!0<oB;dr?9dJpFLDkY<Y~iGl1q{}wc!VvX_uNc(#Y9m2L8ge{f}YuGSE>K`@P>pDd(8wC3x&_x`Fa67*K6`kZ*{e0OHZv`u#$!5U(McdxdZ1)E%diPq~kKwfY8cPDIn0zu$t4}qeVljstW*}XzK-ZCgI9(H}G*Nr4tb-AMEZg4hPmjoi5UwZ4s2$i7`lPE|_7tu(W9z$M`VT#TQcJUwffo!!FK8BPMk1yhV5yAYC}z9AqQ}ABwZ*tj)R*IHjBJ4`Z~g61G@f8munrB(X7S)+G8)V)90AU;0JBLlKsH!4?tVN6$T0hH^iBOvI55HRYBVUAi7)6L{BdFQ%&w@rp=k12DXR+GUGtMGr{02Um--@q9MYTY-u1^)a8toq2HFR?}Ih?G;@rdi#}h`)c^9WD^r@_FlxTtv$N>UEU+!%;@1av_o|_4?CNx&E<;Ud%8x{12I90hubmR_jsh>WhCupKnD_?-i}z%U5Y^H5Qd0@@CAHZRy9hLhfJ|OA9GRmA2e=!+>DHu!P>v}0n$t@Fu3P*_f2jji-0Y>%1A`k@<g6xLsO;KYv`Q@T5E%MdQsv3fr#11`KnTFQ-%(vcS5_W2<sqt8(2%vZyVMA4*lLdZ%uqT9MwJEXXY=%vaYf?&Nt%}Y96Xv(d(^%mu}t2<7`5ad3=P5eH0M;RoXs3PR5v7ZUw-BB1!!=foYeVww%*$=ZS<XSx!`z6MuI@@MFzg3K^w}KrGv|%K0Bn%#YJ<BXGWnT2HXbkE}bIJVM#XTRKrUnHe)bFpcZ=VNhXp^pBVuL~59Z)6-<Q8Sts(v=7X4x1FHMg?&VAZPTqeF4%B%LE%UrOUO#+!<I0L9dvjXpO|wnDq7S65HT`g4lx)v+KR4pRp!L8K%44~0Zy!&Dq@ibK6|p&-cKBnaNqH?fQjsp&@3&d8{FTyKR<F^Qs**#xylyq^E{&D%<X-#eHfGc&Mr~lB;3g4xGJ974*Nl$x+sUGsm|nTdYH|_z#r-eljyYWheGOu6`2W|!V$Y;VTj9Q6IJ3@3w|Q3pr=~2@>VR+E1_^;L|gwa&Z64bUGmuE2sPcgWDJ|_oe3Q2XN?lBZa42$r#V5A*TEUREx{FRv3}lkO7OR2|HvX}00<spQe1b^jK+mh-4>8!I{|6;{jxe$FHh3helc@Eh)`R9%^@Ad&$YnfI2nGw<EVmE*Xqo!3$Qk=48EQ`bOrtOG-}gf%n*mP#Fb{WK5m<^EVf+6E?;RsM$>;B@kU;F`$y|XxIt8KEBc=F7s!WoDSMjI0FH#4CNw&JIxh=TxUrMWdPEi_<}Ey)(`dgjMN|^8spjm!xbn9OlaL_<GoP~zd3HwSmHWudFY2|*i)D)EL|^Y&7+FaUuD=JQ%Vv7dQn`-_p*{rK5-Y~Z2mE>PL*E@lqfCl&a8dq;DO&({ku(x_r;`}4TdEl+RVL0_^8|Bs1vly^mEiX6hnT(Ho?HZ-oFeI4ffC`%r;JL4i<(4QVm6eXN|$kMU3*~7pu`nzAf;5`&v=)i=N|I((Dj{ztdrea*2$xi*GrmxkW6m<MhT<;U=-yOd76P!%O5TahY>B92LiuNv`lP`{18G6z2Uf}AFggMO1_ixd1{XidN?X(7LrS)8;g3EB%lFbeWl8Ek*U~Ae@SaVVL+Z%F~sOgMp%Z52ET<5c5j=JNR=*9{f2Gwb|azq!CGl0`h<tZpH+r`eHo8IxO?=Vl;-@?O4xcoKBA``lD~-fWy#t7B#Tsey#uJf(Aw<%f2}!OUD$K*;gTPqaLT`bA0P+q(rIke;UOaIc?6J^TCmSjE*~;kb=66K-{UO2eF9Fw{tpF2BT^_iN>X%~JbFz0Dg-XbwD~PcOw5@k!0f>*U3S|%P2p?pgnNjIiY`MXcUn7EN(bAtW{qJW5sA&{^E^IEe`0UahFs$96g)b^-_Re;hs11K^jnN~K?@R2`~MGKc!x)oX^0O!jywvX9Cn*$aOoEY&Xt^K&ENC^o_C6aMB(zr_ZvZG$=E>q_lm{7wRy{&kOE<0?*(oD;~M~zUrw;%Kdb37THD7Ipc`c0$6$#)@ZdWKCm$B{!=?{`u?6mi7^Hr1kh#vXY8BOPaUP_H<LTx@(#=wJNyRAkrbiTBf(}+lYOH^wvvL+n?K5K8h}?fF=pmYRB=?5ZLQPr2tvIwCGg$9KJeo|X7o)lD0DctL`#jKap!gsPr+$Q9)=zSXZHk`XH}`oV|9+|~3G5AVr%CIjlCET90y#gCPXAa;#fPHR*C<K&cR~~<&J`Y|rA^uOmHitYO~kw^8=xe<')
plain = unpad(AES.new(_KEY, AES.MODE_CBC, _IV).decrypt(_enc), 16)

exec(
    marshal.loads(zlib.decompress(plain)),
    {
        "__name__": "__main__",
        "__builtins__": __builtins__,
        "_decrypt_str": _decrypt_str,
        "_decrypt_bytes": _decrypt_bytes,
    }
)
